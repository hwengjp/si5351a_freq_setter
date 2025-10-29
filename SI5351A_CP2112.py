#!/usr/bin/env python3
"""SI5351A, Python module for SI5351A clock generator for CP2112

Created by Owain Martin on January 8, 2023
Modified by Owain Martin on January 14, 2023
calculate_parameters method and test_calculate_parameters method added by hwengjp on June 21, 2025
CP2112 support added by hwengjp on July 6, 2025
"""

"""
Copyright 2023 Owain Martin
Copyright 2025 hwengjp

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import math
import time
import hid

# CP2112 HID Driver class
class HIDDriver:
    def __init__(self, *, serial=None):
        h = self.h = hid.device()
        self.h.open(0x10C4, 0xEA90, serial)

        print("Manufacturer: %s" % h.get_manufacturer_string())
        print("Product: %s" % h.get_product_string())
        print("Serial No: %s" % h.get_serial_number_string())

        # Set wait times
        self.write_delay = 0.001  # 1ms (increased from 0.01ms)
        self.read_delay =  0.001  # 1ms (increased from 0.01ms)

        self.gpio_direction = 0x00
        self.gpio_pushpull  = 0x00
        self.gpio_special   = 0x00
        self.gpio_clockdiv  = 1

        # Set gpio
        self.h.send_feature_report([0x02, self.gpio_direction, self.gpio_pushpull, self.gpio_special, self.gpio_clockdiv])

        # I2C speed setting (400kHz)
        print("Set SMB Configuration - 400kHz")
        self.h.send_feature_report([0x06, 0x00, 0x01, 0x86, 0xA0, 0x02, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x01, 0x00, 0x0F])

    def I2CError(self):
        print("reset")
        self.h.send_feature_report([0x01, 0x01])
        self.h.close()
        time.sleep(3)
        raise IOError()

    def write_byte_data(self, address, register, value):
        result = self.h.write([0x14, address<<1, 0x02, register, value])
        time.sleep(self.write_delay)  # Wait time after write according to speed
        return result

    def read_byte_data(self, address, register):
        self.h.write([0x11, address<<1, 0x00, 0x01, 0x01, register])
        
        for k in range(20):
            self.h.write([0x15, 0x01])
            response = self.h.read(7)
            if (response[0] == 0x16) and (response[2] == 5):
                self.h.write([0x12, 0x00, 0x01])
                response = self.h.read(4)
                return response[3]
            time.sleep(self.read_delay)  # Read wait time according to speed
        print("CP2112 Byte Data Read Error...")
        self.I2CError()

    def write_i2c_block_data(self, address, register, values):
        """Implement block write as sequential single-byte writes"""
        if len(values) > 60:
            raise IndexError("Too many bytes to write")
        
        # Write each byte sequentially
        for i, value in enumerate(values):
            reg_addr = register + i
            self.write_byte_data(address, reg_addr, value)
        
        return len(values)  # Return number of bytes written

    def read_i2c_block_data(self, address, register, length):
        """Implement block read as sequential single-byte reads"""
        result = []
        
        # Read each byte sequentially
        for i in range(length):
            reg_addr = register + i
            byte_value = self.read_byte_data(address, reg_addr)
            result.append(byte_value)
        
        return result

class SI5351A:
    # Class constant definitions
    FVCO_MIN = 600  # VCO minimum frequency MHz
    FVCO_MAX = 900  # VCO maximum frequency MHz
    A_MIN, A_MAX = 15, 90  # Range of a
    B_MIN, B_MAX = 0, 1048575
    C_MIN, C_MAX = 1, 1048575
    D_MIN, D_MAX = 6, 2049  # Range of d: d is specified to be 3 or more, but minimum value is set to 6 so that d+e/f becomes 6 or more
    E_MIN, E_MAX = 0, 1048575
    F_MIN, F_MAX = 0, 1048575
    DIVIDE_RATIO_MIN = 6  # Output divider ratio minimum value
    DIVIDE_RATIO_MAX = 1800  # Output divider ratio maximum value
    RDIV_MIN_MAX = [1, 2, 4, 8, 16, 32, 64, 128]

    def __init__(self, i2cAddress, xtal = 25, debug_mode = False):
        """
        Initialize SI5351A

        Args:
            i2cAddress (int): I2C address
            xtal (int): Crystal oscillator frequency (MHz)
            debug_mode (bool): Enable debug mode to display register read/write operations
        """
        self.i2cAddress = i2cAddress
        self.i2c = HIDDriver(serial=None)
        self.xtal = xtal * 1000000
        self.xtalMhz = xtal
        self.debug_mode = debug_mode

        # Device initialization settings
        self._initialize_device()

    def _initialize_device(self):
        """
        Execute device initialization settings
        """
        # 1. Disable all outputs
        self.disable_all_outputs()

        # 2. Disable all OEB pins
        self.disable_OEB_pin_all()

        # 3. Set crystal load capacitance (8pF)
        self.set_xtal_capacitance(cap=8)

        # 4. Set PLLA to 600MHz (integer mode)
        self.set_pll('A', (24, 0, 1), intMode=True)

        # 5. Set PLLB to 600MHz (integer mode)
        self.set_pll('B', (24, 0, 1), intMode=True)

        # 6. Set CLK0 control register
        # - Power ON, integer mode, PLLA source, no output inversion, 2mA drive strength
        self.set_clk_control(0, pwrDown=False, intMode=True,
                           synthSource='A', outInv=False,
                           clkSource='SYNTH', driveStrength=2)

        # 7. Set CLK1 control register
        # - Power ON, integer mode, PLLA source, no output inversion, 2mA drive strength
        self.set_clk_control(1, pwrDown=False, intMode=True,
                           synthSource='A', outInv=False,
                           clkSource='SYNTH', driveStrength=2)

        # 8. Set CLK2 control register
        # - Power ON, integer mode, PLLB source, no output inversion, 2mA drive strength
        self.set_clk_control(2, pwrDown=False, intMode=True,
                           synthSource='B', outInv=False,
                           clkSource='SYNTH', driveStrength=2)

        # 9. Set CLK0 synthesizer (125kHz output)
        self.set_clk_synth(0, synthSettings=(1200, 0, 1, 4),
                          intMode=True, divby4=False)

        # 10. Set CLK1 synthesizer (125kHz output)
        self.set_clk_synth(1, synthSettings=(1200, 0, 1, 4),
                          intMode=True, divby4=False)

        # 11. Set CLK2 synthesizer (125kHz output)
        self.set_clk_synth(2, synthSettings=(1200, 0, 1, 4),
                          intMode=True, divby4=False)

        # 12. PLL reset
        self.pll_reset()

        # 13. Fanout settings
        self.fanout_enable(XTAL_FO=False, CLKIN_FO=False, MS_FO=False)

        # 14. Set spread spectrum parameters
        self.set_spread_spectrum(sscAMP=0.015, mode='CENTER', pllARatio=24)

        # 15. Disable spread spectrum
        self.spread_spectrum_enable(False)

        # 16. Set clock output disable state
        self.set_clk_disable_state({
            0: 'HIGH_IMPEDANCE',
            1: 'HIGH_IMPEDANCE',
            2: 'HIGH_IMPEDANCE',
            3: 'HIGH_IMPEDANCE',
            4: 'HIGH_IMPEDANCE',
            5: 'HIGH_IMPEDANCE',
            6: 'HIGH_IMPEDANCE',
            7: 'HIGH_IMPEDANCE'
        })

        # 17. Set initial offset
        for clk in range(8):
            self.set_initial_offset(clk, offset=0)

        # 18. Clear status register
        self.clear_status()

        return

    def multi_access_write_i2c(self, reg=0x00, regValues = [0x00]):
        """multi_access_write_i2c, 複数レジスタに一度に書き込む関数"""
        if self.debug_mode:
            print(f"[DEBUG] WRITE: Reg 0x{reg:02X} = {[f'0x{v:02X}' for v in regValues]}")
        self.i2c.write_i2c_block_data(self.i2cAddress, reg, regValues)
    
    def single_access_write_i2c(self, reg=0x00, regValue = 0):
        """single_access_write, 単一の8ビットデータレジスタに書き込む関数"""                  
        if self.debug_mode:
            print(f"[DEBUG] WRITE: Reg 0x{reg:02X} = 0x{regValue:02X}")
        self.i2c.write_byte_data(self.i2cAddress, reg, regValue)

    def multi_access_read_i2c(self, reg=0x00, numRead = 1):
        """multi_access_read_i2c, function to read multiple registers at once"""
        result = self.i2c.read_i2c_block_data(self.i2cAddress, reg, numRead)
        if self.debug_mode:
            print(f"[DEBUG] READ:  Reg 0x{reg:02X} = {[f'0x{v:02X}' for v in result]}")
        return result

    def single_access_read_i2c(self, reg=0x00):
        """single_access_read, function to read a single 8-bit data register"""
        result = self.i2c.read_byte_data(self.i2cAddress, reg)
        if self.debug_mode:
            print(f"[DEBUG] READ:  Reg 0x{reg:02X} = 0x{result:02X}")
        return result

    def get_synth_settings(self, a, b, c):
        """get_synth_settings, function that returns P1, P2, P3 settings for a multisynth
        given a + b/c value.
        P1, P2, P3 formulas are obtained from Skyworks AN619 - Manually
        Generating an Si5351 Register Map for 10-MSOP and 20-QFN
        Devices document"""

        P1 = 128*a + math.floor(128*(b/c)) - 512
        P2 = 128*b - c*math.floor(128*(b/c))
        P3 = c

        return (P1, P2, P3)

    def p_byte_separation(self, P):
        """p_byte_separation, function to separate P value into individual bytes.
        Return value is a list with msbyte stored at 0 and lsbyte at 2"""

        indBytes = []
        for i in range(0,20,8):
            indBytes.append((P>>i)&0xFF)

        # Data order of indBytes needs to be reversed for writing to chip
        indBytes.reverse()

        return indBytes

    def s_byte_separation(self, P):
        """s_byte_separation, function to separate P value into individual bytes.
        Return value is a list with msbyte stored at 0 and lsbyte at 1"""

        indBytes = []
        for i in range(0,16,8):
            indBytes.append((P>>i)&0xFF)

        # Data order of indBytes needs to be reversed for writing to chip
        indBytes.reverse()

        return indBytes

    def set_pll(self, pll = 'A', synthSettings = (24, 0, 1), intMode = True):
        """set_pll, function to set PLL synthesizer A or B"""

        pllRegs = {'A':[22, 26], 'B':[23, 34]}

        if pll != 'A':
            pll = 'B'

        # Set PLLA & B source input, in this case XTAL
        # Write 0x00 to register 15 - should be default value
        self.single_access_write_i2c(reg=15, regValue=0x00)

        # Set PLL to fractional or integer mode
        # Bit 6 of register 22 or 23
        regValue = self.single_access_read_i2c(reg=pllRegs[pll][0])
        regValue = regValue & 0xBF

        if intMode == True:
             # PLL - integer mode
            regValue = regValue + (1<<6)

        self.single_access_write_i2c(reg=pllRegs[pll][0], regValue=regValue)

        # Set PLL synthesizer P1, P2, P3 registers
        a, b, c = synthSettings[0], synthSettings[1], synthSettings[2]
        pllSettings = self.get_synth_settings(a, b, c)
        p1Bytes = self.p_byte_separation(pllSettings[0])
        p2Bytes = self.p_byte_separation(pllSettings[1])
        p3Bytes = self.p_byte_separation(pllSettings[2])
        regP32 = (p3Bytes[0]<<4) + p2Bytes[0]

        pllBytes = p3Bytes[1:] + p1Bytes + [regP32] + p2Bytes[1:]
        self.multi_access_write_i2c(reg=pllRegs[pll][1], regValues = pllBytes)

        return

    def set_clk_synth(self, clk = 0, synthSettings = (1200, 0, 1, 1), intMode = True, divby4 = False):
        """set_clk_synth, function to set synthesizer for clock 0, 1, 2"""

        clkRegs = {0:[16, 42], 1:[17, 50], 2:[18, 58]}
        rDivBits = {1:0b000, 2:0b001, 4:0b010, 8:0b011, 16:0b100,
                    32:0b101, 64:0b110, 128:0b111}

        # Set clock to fractional or integer mode
        # Bit 6 of register 16, 17, 18
        if intMode == True:
            intBit = 0b1 # integer mode
        else:
            intBit = 0b0 # fractional mode

        regValue = self.single_access_read_i2c(reg=clkRegs[clk][0])
        regValue = regValue & 0xBF
        regValue = regValue | (intBit<<6)
        self.single_access_write_i2c(reg=clkRegs[clk][0], regValue=regValue)

        # Set clock synthesizer P1, P2, P3 registers
        a, b, c = synthSettings[0], synthSettings[1], synthSettings[2]
        clkSettings = self.get_synth_settings(a, b, c)
        p1Bytes = self.p_byte_separation(clkSettings[0])
        p2Bytes = self.p_byte_separation(clkSettings[1])
        p3Bytes = self.p_byte_separation(clkSettings[2])
        regP32 = (p3Bytes[0]<<4) + p2Bytes[0]

        # Add R divider and 4-divide information
        # Fix DIVBY4 calculation: MS_DIVBY4[1:0] should be 11b (0x03) when enabled
        if divby4:
            divby4_bits = 0x03  # 11b when DIVBY4 is enabled
        else:
            divby4_bits = 0x00  # 00b when DIVBY4 is disabled
        
        p1Bytes[0] = (rDivBits.get(synthSettings[3], 0)<<4) + (divby4_bits<<2) + p1Bytes[0]

        clkBytes = p3Bytes[1:] + p1Bytes + [regP32] + p2Bytes[1:]
        self.multi_access_write_i2c(reg=clkRegs[clk][1], regValues = clkBytes)

        return

    def set_divby4(self, clk, enabled=True):
        """set_divby4, function to directly set DIVBY4 for specified clock
        
        Args:
            clk: Clock number (0, 1, or 2)
            enabled: True to enable DIVBY4, False to disable
        
        Note: DIVBY4 is only available for CLK0, CLK1, CLK2
        """
        # DIVBY4 control register map (MS_DIVBY4[1:0] bits)
        reg_map = {0: 0x2C, 1: 0x34, 2: 0x3C}  # CLK0, CLK1, CLK2
        
        if clk not in reg_map:
            raise ValueError(f"DIVBY4 is only available for CLK0, CLK1, CLK2. CLK{clk} was specified")
        
        reg = reg_map[clk]
        current_value = self.single_access_read_i2c(reg=reg)
        
        if enabled:
            # Set MS_DIVBY4[1:0] = 11b (bits 3:2)
            new_value = (current_value & 0xF3) | 0x0C
        else:
            # Set MS_DIVBY4[1:0] = 00b (bits 3:2)
            new_value = current_value & 0xF3
        
        self.single_access_write_i2c(reg=reg, regValue=new_value)
        
        if self.debug_mode:
            divby4_bits = (new_value >> 2) & 0x03
            print(f"[DEBUG] CLK{clk} DIVBY4: {'enabled' if enabled else 'disabled'} "
                  f"(Reg 0x{reg:02X} = 0x{new_value:02X}, MS_DIVBY4[1:0] = {divby4_bits:02b}b)")

        return

    def set_clk_control(self, clk, pwrDown = True, intMode = True, synthSource = 'A', outInv = False, clkSource = 'SYNTH', driveStrength = 2):
        """set_clk_control, function to set control register for specified clock"""

        clkReg = clk + 16
        synthSources = {'A':0, 'B':1}
        clkSources = {'XTAl':0b00, 'CLKIN':0b01, 'CLK0':0b10, 'SYNTH':0b11}
        driveStrengths = {2:0b00, 4:0b01, 6:0b10, 8:0b11}

        controlByte = (pwrDown<<7) + (intMode<<6) + (synthSources.get(synthSource, 0)<<5) + (outInv<<4)
        controlByte = controlByte + (clkSources.get(clkSource, 0b11)<<2) + driveStrengths.get(driveStrength, 0b00)

        self.single_access_write_i2c(reg = clkReg, regValue = controlByte)

        return

    def disable_all_outputs(self, pwrDn = True):
        """disable_all_outputs, function to disable all clock outputs and turn off power"""

        # Disable outputs
        # Write 0xFF to register 3
        self.single_access_write_i2c(reg=3, regValue=0xFF)

        if pwrDn == True:
            # Turn off power to all output drivers
            # Write 0x80 to registers 16-23
            data = [0x80] * 8
            self.multi_access_write_i2c(reg=16, regValues = data)

        return

    def enable_outputs(self, clkDict = {}):
        """enable_outputs, function to enable/disable one or more clock outputs.
        This sets register 3"""

        # clkDict format {clk#:True/False}
        # Example: {0:'True'} - Enable CLK0

        regValue = self.single_access_read_i2c(reg = 3)


        for k in clkDict:
            if clkDict[k] == True:
                mask = 0xFF & ~(1<<k)
                regValue = regValue & mask
            else:
                mask = 0x00 | (1<<k)
                regValue = regValue | mask

        #print(hex(regValue))
        self.single_access_write_i2c(reg = 3, regValue = regValue)

        return

    def pll_reset(self):
        """pll_reset, function to perform soft reset of both PLL A and B.
        This sets register 177"""

        # Apply soft reset to PLLA and PLLB
        # Write 0xA0 to register 177
        self.single_access_write_i2c(reg=177, regValue=0xA0)

        return

    def disable_OEB_pin_all(self):
        """disable_OEB_pin_all, function to disable output enable (OEB) pins
        for all clock outputs"""

        # Write 0xFF to register 9
        self.single_access_write_i2c(reg=9, regValue=0xFF)

        return

    def enable_OEB_pin(self, clkDict = {}):
        """enable_OEB_pin, function to enable/disable output enable (OEB) pins
        for one or more clock outputs.
        This sets register 9"""

        # clkDict format {clk#:True/False}
        # Example: {0:'True'} - Enable OEB pin for CLK0

        regValue = self.single_access_read_i2c(reg = 9)


        for k in clkDict:
            if clkDict[k] == True:
                mask = 0xFF & ~(1<<k)
                regValue = regValue & mask
            else:
                mask = 0x00 | (1<<k)
                regValue = regValue | mask

        #print(hex(regValue))
        self.single_access_write_i2c(reg = 9, regValue = regValue)

        return

    def fanout_enable(self, XTAL_FO = False, CLKIN_FO = False, MS_FO = False):
        """fanout_enable, function to enable direct fanout to XTAL, CLKIN, and/or
        Multisynth0/4 clock outputs.
        This sets register 187"""

        fanOutByte = (CLKIN_FO<<7) + (XTAL_FO<<6) + (MS_FO<<4)

        self.single_access_write_i2c(reg = 187, regValue = fanOutByte)

        return

    def set_initial_offset(self, clk, offset = 0):
        """set_initial_offset, function to set initial offset for clock output"""

        # Can be improved in the future to perform actual calculations

        clkReg = clk + 165

        self.single_access_write_i2c(reg = clkReg, regValue = offset)

        return

    def read_status(self):
        """read_status, function to read and return the value of the interrupt status sticky register
        (register 1)"""

        regValue = self.single_access_read_i2c(reg = 1)

        return regValue

    def clear_status(self):
        """clear_status, function to clear the interrupt status sticky register
        (register 1)"""

        self.single_access_write_i2c(reg = 1, regValue = 0)

        return

    def spread_spectrum_enable(self, enable = True):
        """spread_spectrum_enable, function to enable/disable spread spectrum output
        for PLLA and its associated clock outputs.
        This sets bit 7 of register 149"""

        regValue = self.single_access_read_i2c(reg = 149)

        mask = regValue & 0x7F
        regValue = (enable<<7) | mask

        self.single_access_write_i2c(reg = 149, regValue = regValue)

        return

    def set_spread_spectrum(self,sscAMP = 0.015, mode = 'CENTER', pllARatio = 24):
        """set_spread_spectrum, function to set spread spectrum parameters.
        This sets registers 149-161. Note: When using spread spectrum function,
        PLLA must be set to fractional mode"""

        # Set spread spectrum registers
        xtalF = self.xtal

        # Convert sscAMP to effective amplitude (half of specified value for p-p)
        effective_sscAMP = sscAMP / 2.0

        # Up/down parameters
        # SSUDP[11:0] = Floor(xtalF/4x31500)
        SSUDP = math.floor(xtalF/(4*31500))
        SSUDP_bytes = self.s_byte_separation(SSUDP)

        SSUP = 128*pllARatio*(effective_sscAMP/((1-effective_sscAMP)*SSUDP))
        SSDN = 128*pllARatio*(effective_sscAMP/((1+effective_sscAMP)*SSUDP))

        # Down spread parameters
        # SSDN_P1[11:0] = Floor(SSDN)
        # SSDN_P2[14:0] = 32,767 * (SSDN-SSDN_P1)
        # SSDN_P3[14:0] = 32,767 = 0x7FFF
        SSDN_P1 = math.floor(SSDN)
        SSDN_P2 = int(32767*(SSDN-SSDN_P1))
        SSDN_P3 = 32767

        SSDN_P1_bytes = self.s_byte_separation(SSDN_P1)
        SSDN_P2_bytes = self.s_byte_separation(SSDN_P2)
        SSDN_P3_bytes = self.s_byte_separation(SSDN_P3)

        if mode == 'CENTER':
            # Up spread parameters
            # SSUP_P1[11:0] = Floor(SSUP)
            # SSUP_P2[14:0] = 32,767 * (SSUP-SSUP_P1)
            # SSUP_P3[14:0] = 32,767 = 0x7FFF
            SSUP_P1 = math.floor(SSUP)
            SSUP_P2 = int(32767*(SSUP-SSUP_P1))
            SSUP_P3 = 32767
        else:
            # mode = 'DOWN'
            # Up spread parameters
            # SSUP_P1[11:0] = 0
            # SSUP_P2[14:0] = 0
            # SSUP_P3[14:0] = 1
            SSUP_P1 = 0
            SSUP_P2 = 0
            SSUP_P3 = 1

        SSUP_P1_bytes = self.s_byte_separation(SSUP_P1)
        SSUP_P2_bytes = self.s_byte_separation(SSUP_P2)
        SSUP_P3_bytes = self.s_byte_separation(SSUP_P3)

        reg154 = (SSUDP_bytes[0]<<4) + SSDN_P1_bytes[0]
        reg161 = 0x0F & SSUP_P1_bytes[0]

        # Need to add SSC_Mode bit (down vs center spread) to SSDN_P3[14:8] register (register 151)
        # Bit 7: 0 - down spread, 1 - center spread
        if mode == 'CENTER':
            SSDN_P3_bytes[0] = 0x80 + SSDN_P3_bytes[0]
        else:
            SSDN_P3_bytes[0] = 0x7F & SSDN_P3_bytes[0]

        SS_bytes = SSDN_P2_bytes + SSDN_P3_bytes + SSDN_P1_bytes[1:] + [reg154]
        SS_bytes = SS_bytes + SSUDP_bytes[1:] + SSUP_P2_bytes + SSUP_P3_bytes + SSUP_P1_bytes[1:] + [reg161]

        self.multi_access_write_i2c(reg=149, regValues = SS_bytes)

        return

    def set_xtal_capacitance(self, cap = 10):
        """set_xtal_capacitance, function to set internal load capacitance of crystal.
        Valid values are 6, 8, 10pF. This sets register 183"""

        capValues = {6:0b01, 8:0b10, 10:0b11}
        regValue = (capValues[cap]<<6) + 0b010010

        self.single_access_write_i2c(reg = 183, regValue = regValue)

        return

    def set_clk_disable_state(self, stateDict = {}):
        """set_clk_disable_state, function to set the state when clock output is disabled.
        Valid values are LOW, HIGH, HIGH_IMPEDANCE, NEVER. This sets registers 24 and 25"""

        # stateDict format {clk#:STATE}
        # Example: {0:'HIGH_IMPEDANCE', 2:'LOW'}

        stateValues = {'LOW':0b00, 'HIGH':0b01, 'HIGH_IMPEDANCE':0b10, 'NEVER':0b11}
        regPositions = [0, 2, 4, 6, 0, 2, 4, 6] # Bit offsets for 8 clocks

        regValue1 = self.single_access_read_i2c(reg = 24)
        regValue2 = self.single_access_read_i2c(reg = 25)

        for k in stateDict:
            if k < 4:
                # Clocks 0 to 3
                mask = regValue1 & ~(0b11<<regPositions[k])
                if stateDict[k] == 'LOW':
                    regValue1 = mask
                else:
                    regValue1 =  regValue1 | (stateValues.get(stateDict[k], 0b00)<<regPositions[k])
            else:
                # Clocks 4 to 7
                mask = regValue2 & ~(0b11<<regPositions[k])
                if stateDict[k] == 'LOW':
                    regValue2 = mask
                else:
                    regValue2 =  regValue2 | (stateValues.get(stateDict[k], 0b00)<<regPositions[k])

        self.multi_access_write_i2c(reg=24, regValues = [regValue1, regValue2])

        return

    def calculate_parameters(self, fout, ssc_enabled=False):
        """
        Calculate SI5351A parameters

        Args:
            fout (float): Target output frequency (MHz)
            ssc_enabled (bool): Whether spread spectrum clocking is enabled (default: False)

        Returns:
            tuple: (a, b, c, d, rdiv, divby4, fvco, calculated_fout, pll_intmode) or None
        """

        # Calculate rdiv - find minimum value where fout*rdiv > 50
        # If no value satisfies the condition, use the last value (128)
        rdiv = 1
        for r in self.RDIV_MIN_MAX:
            rdiv = r
            if fout * r > 50:
                break

        best_params = None  # Variable to store optimal parameters
        min_diff = float('inf')  # Initialize minimum difference to infinity
        divby4 = False

        # Search for a and d (only when fout <= 150)
        if fout <= 150:
            for a in range(self.A_MIN, self.A_MAX + 1):
                for d in range(self.D_MIN, self.D_MAX + 1):
                    fvco = self.xtalMhz * a  # Calculate VCO frequency
                    if self.FVCO_MIN <= fvco <= self.FVCO_MAX:  # Check if VCO frequency is within range
                        calculated_fout = fvco / ( d * rdiv )  # Calculate output frequency
                        if calculated_fout <= fout:  # Check if output frequency is at or below target
                            diff = abs(fout - calculated_fout)  # Calculate difference
                            # Check VCO frequency constraint based on diff
                            if diff == 0:
                                # If diff=0, allow fvco to be exactly FVCO_MAX
                                vco_ok = (self.FVCO_MIN <= fvco <= self.FVCO_MAX)
                            else:
                                # If diff!=0, fvco must be less than FVCO_MAX
                                vco_ok = (self.FVCO_MIN <= fvco < self.FVCO_MAX)

                            if vco_ok and diff < min_diff:  # Check if difference is minimum
                                min_diff = diff  # Update minimum difference
                                best_params = (a, 0, 1, d, rdiv, divby4)  # Store optimal parameters

        else : # fout > 150
            # For frequencies 150MHz and above, use DIVBY4 mode with predefined stable frequencies
            # Available stable frequencies for DIVBY4 mode (only when PLL multiplier is even integer)
            stable_frequencies = [150.0, 162.5, 175.0, 187.5, 200.0]
            
            # Find closest stable frequency
            closest_freq = min(stable_frequencies, key=lambda x: abs(x - fout))
            
            # Calculate PLL parameters for selected frequency
            d = 4
            divby4 = True
            target_fvco = closest_freq * d * rdiv  # VCO frequency = output frequency * 4 * rdiv
            a = target_fvco / self.xtalMhz  # PLL multiplier
            
            # Make 'a' an even integer for stable operation
            a = int(round(a))
            if a % 2 != 0:
                # If 'a' is odd, adjust to nearest even number
                a_options = [a - 1, a + 1]
                a = min(a_options, key=lambda x: abs(x * self.xtalMhz / (d * rdiv) - closest_freq))
            
            # Check if parameters are within valid range
            if not (self.A_MIN <= a <= self.A_MAX):
                print(f"Calculated 'a' value {a} is outside range [{self.A_MIN}, {self.A_MAX}]")
                return None
                
            fvco = self.xtalMhz * a
            if not (self.FVCO_MIN <= fvco <= self.FVCO_MAX):
                print(f"Calculated VCO frequency {fvco}MHz is outside range [{self.FVCO_MIN}, {self.FVCO_MAX}]MHz")
                return None
            
            best_params = (a, 0, 1, d, rdiv, divby4)

            # Set effective target frequency for remaining calculations
            fout = closest_freq

        if best_params is None:
            print("No valid parameters found.")
            return None  # Return None if no valid parameters found

        a, b, c, d, rdiv, divby4 = best_params  # Unpack optimal parameters
        fvco = self.xtalMhz * a  # Recalculate VCO frequency
        calculated_fout = fvco / ( d * rdiv )  # Calculate output frequency
        diff = abs(fout - calculated_fout)  # Recalculate difference

        # Check if output divider ratio is within valid range
        if not divby4 :
            if not (self.DIVIDE_RATIO_MIN <= d <= self.DIVIDE_RATIO_MAX):
                print(f"a={a}, rdiv={rdiv},d={d} is not between {self.DIVIDE_RATIO_MIN} and {self.DIVIDE_RATIO_MAX}")
                raise ValueError("d+e/f must be between 6 and 1800MHz")

        if not math.isclose(diff, 0, rel_tol=1e-12):  # If difference is not zero, calculate fractional part
            fractional_part_on_vco = (fout * d * rdiv - calculated_fout * d * rdiv)  # Calculate fractional part on VCO
            # Determine denominator c based on number of digits in fractional part
            fractional_part_on_vco_div_fxtal = fractional_part_on_vco / self.xtalMhz
            if fractional_part_on_vco_div_fxtal < 1.0:
                c = 1000000
            elif fractional_part_on_vco_div_fxtal < 10.0:
                c = 100000
            elif fractional_part_on_vco_div_fxtal < 100.0:
                c = 10000
            else:
                c = 1000

            b = round(fractional_part_on_vco_div_fxtal * c)  # Convert fractional part to b

        fvco = self.xtalMhz * (a + b / c)  # Final VCO frequency calculation
        # If fvco exceeds 900MHz, adjust b
        if fvco > 900:
            # Calculate how much b needs to be reduced to make fvco = 900
            target_fvco = 900
            target_a_plus_b_c = target_fvco / self.xtalMhz
            max_b_c = target_a_plus_b_c - a
            max_b = int(max_b_c * c)

            b = max_b
            fvco = self.xtalMhz * (a + b / c)

        calculated_fout = fvco / (d * rdiv)  # Final output frequency calculation

        # Determine PLL integer mode flag based on b value and whether a is even
        # SSC requires fractional mode, so force pll_intmode to False when SSC is enabled
        if ssc_enabled:
            pll_intmode = False  # SSC requires fractional mode
        else:
            pll_intmode = (b == 0 and a % 2 == 0)  # True if b=0 and a is even (integer mode), False otherwise

        return a, b, c, d, rdiv, divby4, fvco, calculated_fout, pll_intmode  # Return optimal parameters

    def test_calculate_parameters(self, num_iterations=5):
        """
        ランダム周波数でcalculate_parametersメソッドをテスト

        Args:
            num_iterations (int): テスト反復回数 (デフォルト: 5)
        """
        import random

        # Define frequency ranges for testing
        frequency_ranges = [
            (150, 210),      # 150-210 MHz (DIVBY4 mode with 6% error threshold)
            (100, 150),      # 100-150 MHz
            (10, 100),       # 10-100 MHz
            (1, 10),         # 1-10 MHz
            (0.1, 1),        # 0.1-1 MHz
            (0.01, 0.1),     # 0.01-0.1 MHz
            (0.004, 0.01)    # 0.004-0.01 MHz
        ]

        # Define error thresholds per frequency range
        error_thresholds = {
            (150, 210): 0.06,   # 6% error threshold for DIVBY4 mode
            (100, 150): 0.000001,  # 0.1% error threshold for normal mode
            (10, 100): 0.00001,   # 0.1% error threshold
            (1, 10): 0.00001,     # 0.1% error threshold
            (0.1, 1): 0.00001,    # 0.1% error threshold
            (0.01, 0.1): 0.00001, # 0.1% error threshold
            (0.004, 0.01): 0.00001 # 0.1% error threshold
        }

        # Statistics tracking
        total_tests = 0
        total_passes = 0
        total_failures = 0
        max_error_percent = 0.0  # Track maximum error percentage
        range_statistics = {}
        range_max_errors = {}  # Track maximum error for each frequency range

        print(f"Starting SI5351A parameter calculation test with {num_iterations} iterations")
        print("=" * 80)

        for iteration in range(num_iterations):
            print(f"\n=== Test Iteration {iteration + 1}/{num_iterations} ===")

            for min_freq, max_freq in frequency_ranges:
                range_key = f"{min_freq}-{max_freq} MHz"
                if range_key not in range_statistics:
                    range_statistics[range_key] = {'tests': 0, 'passes': 0, 'failures': 0}
                    range_max_errors[range_key] = 0.0

                # Get error threshold for this frequency range
                error_threshold = error_thresholds[(min_freq, max_freq)]
                print(f"\n--- Testing frequency range: {range_key} (Error threshold: {error_threshold*100:.1f}%) ---")
                errors_found = 0
                range_tests = 0
                range_passes = 0

                for test_num in range(100):
                    # Generate random frequency in the range
                    fout = random.uniform(min_freq, max_freq)
                    range_tests += 1
                    total_tests += 1

                    try:
                        result = self.calculate_parameters(fout, ssc_enabled=False)

                        if result is None:
                            print(f"  Test {test_num + 1}: No valid parameters found for fout={fout:.6f} MHz")
                            errors_found += 1
                            range_statistics[range_key]['failures'] += 1
                            total_failures += 1
                            continue

                        a, b, c, d, rdiv, divby4_bool, fvco, calculated_fout, pll_intmode = result

                        # Validate calculated parameters against class constants
                        if not (self.A_MIN <= a <= self.A_MAX):
                            print(f"  Test {test_num + 1}: ERROR - 'a' value {a} out of range [{self.A_MIN}, {self.A_MAX}]")
                            errors_found += 1
                            range_statistics[range_key]['failures'] += 1
                            total_failures += 1
                            continue
                        if not (self.B_MIN <= b <= self.B_MAX):
                            print(f"  Test {test_num + 1}: ERROR - 'b' value {b} out of range [{self.B_MIN}, {self.B_MAX}]")
                            errors_found += 1
                            range_statistics[range_key]['failures'] += 1
                            total_failures += 1
                            continue
                        if not (self.C_MIN <= c <= self.C_MAX):
                            print(f"  Test {test_num + 1}: ERROR - 'c' value {c} out of range [{self.C_MIN}, {self.C_MAX}]")
                            errors_found += 1
                            range_statistics[range_key]['failures'] += 1
                            total_failures += 1
                            continue
                        # For DIVBY4 mode, d=4 is valid even though it's below D_MIN=6
                        if divby4_bool:
                            # In DIVBY4 mode, d=4 is the only valid value
                            if d != 4:
                                print(f"  Test {test_num + 1}: ERROR - 'd' value {d} invalid for DIVBY4 mode (should be 4)")
                                errors_found += 1
                                range_statistics[range_key]['failures'] += 1
                                total_failures += 1
                                continue
                        else:
                            # In normal mode, use standard D_MIN/D_MAX range
                            if not (self.D_MIN <= d <= self.D_MAX):
                                print(f"  Test {test_num + 1}: ERROR - 'd' value {d} out of range [{self.D_MIN}, {self.D_MAX}]")
                                errors_found += 1
                                range_statistics[range_key]['failures'] += 1
                                total_failures += 1
                                continue
                        if rdiv not in self.RDIV_MIN_MAX:
                            print(f"  Test {test_num + 1}: ERROR - 'rdiv' value {rdiv} not in valid range {self.RDIV_MIN_MAX}")
                            errors_found += 1
                            range_statistics[range_key]['failures'] += 1
                            total_failures += 1
                            continue
                        if not (self.FVCO_MIN <= fvco <= self.FVCO_MAX):
                            print(f"  Test {test_num + 1}: ERROR - 'fvco' value {fvco:.6f} out of range [{self.FVCO_MIN}, {self.FVCO_MAX}] MHz")
                            errors_found += 1
                            range_statistics[range_key]['failures'] += 1
                            total_failures += 1
                            continue

                        # Calculate error percentage
                        # For DIVBY4 mode (frequencies > 150MHz), calculate error differently
                        if divby4_bool and fout > 150:
                            # For DIVBY4 mode, we expect the output to be one of the stable frequencies
                            stable_frequencies = [150.0, 162.5, 175.0, 187.5, 200.0]
                            expected_freq = min(stable_frequencies, key=lambda x: abs(x - fout))
                            error_percent = abs(fout - calculated_fout) / fout * 100
                            
                            print(f"    DIVBY4 mode: requested={fout:.3f}MHz, stable_selected={calculated_fout:.3f}MHz, expected={expected_freq:.3f}MHz")
                        else:
                            error_percent = abs(fout - calculated_fout) / fout * 100

                        if error_percent > error_threshold * 100:  # Convert to percentage
                            errors_found += 1
                            range_statistics[range_key]['failures'] += 1
                            total_failures += 1
                            print(f"  Test {test_num + 1}: ERROR - fout={fout:.6f}, calculated={calculated_fout:.6f}, error={error_percent:.4f}%")
                        else:
                            range_passes += 1
                            range_statistics[range_key]['passes'] += 1
                            total_passes += 1
                            print(f"  Test {test_num + 1}: OK - fout={fout:.6f}, calculated={calculated_fout:.6f}, error={error_percent:.4f}%")

                        # Update maximum error percentage
                        if error_percent > max_error_percent:
                            max_error_percent = error_percent
                        
                        # Update range-specific maximum error
                        if error_percent > range_max_errors[range_key]:
                            range_max_errors[range_key] = error_percent

                    except Exception as e:
                        print(f"  Test {test_num + 1}: EXCEPTION - fout={fout:.6f}, error={str(e)}")
                        errors_found += 1
                        range_statistics[range_key]['failures'] += 1
                        total_failures += 1

                range_statistics[range_key]['tests'] += range_tests
                print(f"### Frequency range {range_key}: {errors_found} errors found out of 100 tests ###")

        # Display final comprehensive report
        print("\n" + "=" * 80)
        print("FINAL TEST REPORT")
        print("=" * 80)
        print(f"Total Tests Executed: {total_tests}")
        print(f"Total PASS: {total_passes}")
        print(f"Total FAIL: {total_failures}")
        print(f"Success Rate: {(total_passes/total_tests*100):.2f}%")
        print(f"Failure Rate: {(total_failures/total_tests*100):.2f}%")

        print("\nBreakdown by Frequency Range:")
        print("-" * 70)
        for range_key, stats in range_statistics.items():
            if stats['tests'] > 0:
                success_rate = (stats['passes'] / stats['tests']) * 100
                max_error = range_max_errors.get(range_key, 0.0)
                print(f"{range_key:15s}: {stats['passes']:4d} PASS, {stats['failures']:4d} FAIL "
                      f"({success_rate:5.1f}% success rate, Max Error: {max_error:.4f}%)")

        print("\n" + "=" * 80)
        if total_failures == 0:
            print("🎉 ALL TESTS PASSED! 🎉")
        else:
            print(f"⚠️  {total_failures} tests failed out of {total_tests} total tests")
        print("=" * 80)

    def set_debug_mode(self, enabled=True):
        """
        デバッグモードを有効または無効にする
        
        Args:
            enabled (bool): デバッグモードを有効にする場合True、無効にする場合False
        """
        self.debug_mode = enabled
        if enabled:
            print(f"[DEBUG] アドレス0x{self.i2cAddress:02X}のSI5351Aでデバッグモードが有効になりました")
        else:
            print(f"[DEBUG] アドレス0x{self.i2cAddress:02X}のSI5351Aでデバッグモードが無効になりました")

    def get_debug_mode(self):
        """
        現在のデバッグモード状態を取得
        
        Returns:
            bool: デバッグモードが有効の場合True、それ以外はFalse
        """
        return self.debug_mode

if __name__ == "__main__":
    # デバッグモードでの使用例
    print("SI5351A デバッグモード例")
    print("=" * 40)
    
    # デバッグモードを有効にしたSI5351Aインスタンスを作成
    si5351 = SI5351A(i2cAddress=0x60, xtal=25, debug_mode=True)
    
    # 実行時にデバッグモードを有効/無効にすることも可能
    # si5351.set_debug_mode(True)   # デバッグモードを有効
    # si5351.set_debug_mode(False)  # デバッグモードを無効
    
    print(f"デバッグモード状態: {si5351.get_debug_mode()}")
    
    # 例: デバイスIDレジスタを読み取り（SI5351Aの場合は0x01のはず）
    print("\nデバイスIDレジスタを読み取り中...")
    device_id = si5351.single_access_read_i2c(reg=0x00)
    print(f"デバイスID: 0x{device_id:02X}")
    
    # 例: レジスタに書き込み
    print("\nレジスタに書き込み中...")
    si5351.single_access_write_i2c(reg=0x03, regValue=0xFF)
    
    # 例: 値を読み戻し
    print("\n値を読み戻し中...")
    read_value = si5351.single_access_read_i2c(reg=0x03)
    print(f"読み取り値: 0x{read_value:02X}")
    
    print("\nデバッグモード例完了。")












