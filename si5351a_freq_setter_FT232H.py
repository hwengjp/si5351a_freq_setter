#!/usr/bin/env python3
"""
SI5351A Clock Generator Frequency Setter for FT232H

Command-line interface for configuring SI5351A clock generator chip

created December 19, 2024 by hwengjp
Based on SI5351A Python module by Owain Martin (created January 8, 2023)
"""

"""
Copyright 2024 hwengjp

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License v3.0.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY. See the GNU General Public License for more details.
"""

import argparse
import os
os.environ['BLINKA_FT232H'] = '1'  # Setting Environmental Variable for FT232H

# ANSI color codes for terminal output
class Colors:
    RED = '\033[91m'        # Red for errors
    GREEN = '\033[92m'      # Green for success
    YELLOW = '\033[93m'     # Yellow for warnings
    BLUE = '\033[94m'       # Blue for info
    MAGENTA = '\033[95m'    # Magenta for DIVBY4 mode
    CYAN = '\033[96m'       # Cyan for frequency differences
    WHITE = '\033[97m'      # White for normal text
    BOLD = '\033[1m'        # Bold text
    UNDERLINE = '\033[4m'   # Underlined text
    RESET = '\033[0m'       # Reset to default color
try:
    import SI5351A_FT232H
except RuntimeError as e:
    if "FT232H device found" in str(e):
        print("Error: FT232H device not found. Please check your USB connection.")
        print("Make sure the FT232H device is properly connected and recognized by your system.")
        exit(1)
    else:
        raise

def main():
    # Main function for SI5351A clock generator configuration

    # Configure ArgumentParser for command line interface
    parser = argparse.ArgumentParser(description='SI5351A clock generator frequency setter for FT232H')
    parser.add_argument('--differential', '-d', type=int, choices=[1, 2], metavar='CHANNEL',
                       help='Enable differential output on specified channel (1 or 2)')
    parser.add_argument('--ssc', '-s', action='store_true', help='Enable Spread Spectrum Clocking')
    parser.add_argument('--amp', '-a', type=float, default=0.015, help='Spread spectrum amplitude (default: 0.015)')
    parser.add_argument('--mode', '-m', type=str, default='DOWN', choices=['CENTER', 'DOWN'], help='Spread spectrum mode (default: DOWN)')
    parser.add_argument('--test', '-t', type=int, default=None, help='Run test mode with specified number of iterations')
    parser.add_argument('fout0', type=float, nargs='?', help='Output frequency 0 (MHz)')
    parser.add_argument('fout2', type=float, nargs='?', help='Output frequency 2 (MHz)')

    args = parser.parse_args()

    # Check for invalid combination: -d 2 with fout2 specified
    if args.differential == 2 and args.fout2 is not None:
        print("Error: Cannot use -d 2 (differential on channel 2) when fout2 is specified.")
        print("Channel 2 cannot be used for both differential output and independent frequency.")
        return

    # Initialize SI5351A device
    try:
        clockGen = SI5351A_FT232H.SI5351A(0x60, debug_mode=False)
    except Exception as e:
        print(f"Error: Failed to initialize SI5351A device: {e}")
        print("Please check the device connection and I2C address.")
        return

    # Test mode: Run frequency calculation tests
    if args.test:
        print(f"Running SI5351A parameter calculation tests with {args.test} iterations...")
        try:
            # Run the test method from SI5351A class
            clockGen.test_calculate_parameters(num_iterations=args.test)
            print("\nTest completed successfully.")
        except Exception as e:
            print(f"Error during test execution: {e}")
        return

    # If no arguments provided, just initialize and return
    if args.fout0 is None:
        print("SI5351A initialized. No frequency configuration applied.")
        return

    # Extract frequency parameters from command line arguments
    fout0 = args.fout0
    fout2 = args.fout2 if args.fout2 is not None else None
    differential_channel = args.differential
    ssc_enabled = args.ssc
    ssc_amp = args.amp
    ssc_mode = args.mode

    # Calculate PLL parameters for Clock 0
    try:
        result0 = clockGen.calculate_parameters(fout0, ssc_enabled=ssc_enabled)
        if result0 is None:
            print(f"Error: Cannot calculate parameters for frequency {fout0} MHz")
            return
        a0, b0, c0, d0, rdiv0, divby4_bool0, fvco0, calculated_fout0, pll_intmode0 = result0
        
        # Display calculated parameters for Clock 0
        print(f"Clock 0 - Calculated parameters: a={a0}, b={b0}, c={c0}, d={d0}, rdiv={rdiv0}, divby4={divby4_bool0}, pll_intmode={pll_intmode0}")
        print(f"Clock 0 - Frequency: Request={fout0}, Actual={round(calculated_fout0,7)}, fvco={round(fvco0,7)}")
        
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Calculate PLL parameters for Clock 2 (if specified)
    if fout2 is not None:
        try:
            result2 = clockGen.calculate_parameters(fout2, ssc_enabled=False)  # SSC only affects PLLA
            if result2 is None:
                print(f"Error: Cannot calculate parameters for frequency {fout2} MHz")
                return
            a2, b2, c2, d2, rdiv2, divby4_bool2, fvco2, calculated_fout2, pll_intmode2 = result2
            
            # Display calculated parameters for Clock 2
            print(f"Clock 2 - Calculated parameters: a={a2}, b={b2}, c={c2}, d={d2}, rdiv={rdiv2}, divby4={divby4_bool2}, pll_intmode={pll_intmode2}")
            print(f"Clock 2 - Frequency: Request={fout2}, Actual={round(calculated_fout2,7)}, fvco={round(fvco2,7)}")
            
        except ValueError as e:
            print(f"Error: {e}")
            return

    # Configure PLLA in fractional mode for Clock 0
    clockGen.set_pll('A', (a0, b0, c0), intMode=pll_intmode0)

    # Configure PLLB in fractional mode for Clock 2 (if specified)
    if fout2 is not None:
        clockGen.set_pll('B', (a2, b2, c2), intMode=pll_intmode2)

    # Configure CLK0 control register
    # Power on, integer mode, PLLA source, no inversion, 8mA drive strength
    clockGen.set_clk_control(0, pwrDown=False, intMode=pll_intmode0, synthSource='A',
                           outInv=False, clkSource='SYNTH', driveStrength=8)

    # Configure CLK1 control register
    if differential_channel == 1:
        # Power on, integer mode, PLLA source, inverted output, 8mA drive strength
        clockGen.set_clk_control(1, pwrDown=False, intMode=pll_intmode0, synthSource='A',
                               outInv=True, clkSource='SYNTH', driveStrength=8)
    else:
        # Power down CLK1 when not in differential mode
        clockGen.set_clk_control(1, pwrDown=True, intMode=pll_intmode0, synthSource='A',
                               outInv=False, clkSource='SYNTH', driveStrength=8)

    # Configure CLK2 control register
    if differential_channel == 2:
        # Power on, integer mode, PLLA source, inverted output, 8mA drive strength
        clockGen.set_clk_control(2, pwrDown=False, intMode=pll_intmode0, synthSource='A',
                               outInv=True, clkSource='SYNTH', driveStrength=8)
    elif fout2 is not None:
        # Power on, integer mode, PLLB source, no inversion, 8mA drive strength
        clockGen.set_clk_control(2, pwrDown=False, intMode=pll_intmode2, synthSource='B',
                               outInv=False, clkSource='SYNTH', driveStrength=8)
    else:
        # Power down CLK2 when not used
        clockGen.set_clk_control(2, pwrDown=True, intMode=pll_intmode0, synthSource='B',
                               outInv=False, clkSource='SYNTH', driveStrength=8)

    # Configure clock synthesizer settings
    clockGen.set_clk_synth(0, synthSettings=(d0, 0, 1, rdiv0), intMode=pll_intmode0, divby4=divby4_bool0)

    if differential_channel == 1:
        clockGen.set_clk_synth(1, synthSettings=(d0, 0, 1, rdiv0), intMode=pll_intmode0, divby4=divby4_bool0)

    if differential_channel == 2:
        clockGen.set_clk_synth(2, synthSettings=(d0, 0, 1, rdiv0), intMode=pll_intmode0, divby4=divby4_bool0)
    elif fout2 is not None:
        clockGen.set_clk_synth(2, synthSettings=(d2, 0, 1, rdiv2), intMode=pll_intmode2, divby4=divby4_bool2)

    # Configure Spread Spectrum Clocking (SSC) if enabled
    if ssc_enabled:
        # SSC configuration for fractional mode
        # sscAMP: spread amplitude (for 1% sscAMP = 0.01)
        # mode: valid values 'CENTER' or 'DOWN'
        # pllARatio: a+b/c ratio used to set PLL A
        # Spread modulation rate is fixed at approximately 31.5 kHz
        ch0_pllARatio = int(a0 + b0/c0)
        clockGen.set_spread_spectrum(sscAMP=ssc_amp, mode=ssc_mode, pllARatio=ch0_pllARatio)

        # Enable spread spectrum
        clockGen.spread_spectrum_enable(True)

    # Reset PLL to apply new settings
    clockGen.pll_reset()

    # Enable configured outputs
    clockGen.enable_outputs({0: True})

    if differential_channel == 1:
        clockGen.enable_outputs({1: True})

    if differential_channel == 2 or fout2 is not None:
        clockGen.enable_outputs({2: True})

    # Display configuration results
    print(f'=== Configuration Results ===')
    
    # Check if Clock 0 frequency differs from requested
    if abs(fout0 - calculated_fout0) > 0.000001:
        print(f'Clock 0: {Colors.MAGENTA}{round(calculated_fout0, 7)} MHz{Colors.RESET}')
    else:
        print(f'Clock 0: {round(calculated_fout0, 7)} MHz')

    if differential_channel == 1:
        if abs(fout0 - calculated_fout0) > 0.000001:
            print(f'Clock 1: {Colors.MAGENTA}{round(calculated_fout0, 7)} MHz{Colors.RESET} Inverted (Differential)')
        else:
            print(f'Clock 1: {round(calculated_fout0, 7)} MHz Inverted (Differential)')

    if differential_channel == 2:
        if abs(fout0 - calculated_fout0) > 0.000001:
            print(f'Clock 2: {Colors.MAGENTA}{round(calculated_fout0, 7)} MHz{Colors.RESET} Inverted (Differential)')
        else:
            print(f'Clock 2: {round(calculated_fout0, 7)} MHz Inverted (Differential)')
    elif fout2 is not None:
        # Check if Clock 2 frequency differs from requested
        if abs(fout2 - calculated_fout2) > 0.000001:
            print(f'Clock 2: {Colors.MAGENTA}{round(calculated_fout2, 7)} MHz{Colors.RESET}')
        else:
            print(f'Clock 2: {round(calculated_fout2, 7)} MHz')

    if ssc_enabled:
        print(f'SSC: sscAMP = {ssc_amp}, mode = {ssc_mode}, pllARatio = {ch0_pllARatio}')

if __name__ == "__main__":
    main()