#!/usr/bin/env python3
"""
Comprehensive I2C diagnostic script for CP2112 and SI5351A
"""

import hid
import time

def i2c_diagnostic():
    """Run comprehensive I2C diagnostic tests"""
    
    print("=== CP2112 I2C Diagnostic Tool ===\n")
    
    try:
        # Initialize CP2112
        h = hid.device()
        h.open(0x10C4, 0xEA90, None)
        
        print("✓ CP2112 Device Found:")
        print(f"  Manufacturer: {h.get_manufacturer_string()}")
        print(f"  Product: {h.get_product_string()}")
        print(f"  Serial No: {h.get_serial_number_string()}")
        
        # Set I2C configuration with slower speed for testing
        print("\n✓ Setting I2C Configuration - 100kHz (slower for testing)")
        h.send_feature_report([0x06, 0x00, 0x01, 0x86, 0xA0, 0x02, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x01, 0x00, 0x0F])
        
        # Test 1: Check if I2C bus is responsive
        print("\n=== Test 1: I2C Bus Responsiveness ===")
        test_addresses = list(range(0x08, 0x78))  # Test all possible addresses
        
        responsive_addresses = []
        
        for addr in test_addresses:
            try:
                # Send a simple read command
                h.write([0x11, addr<<1, 0x00, 0x01, 0x01, 0x00])
                
                # Check for response
                h.write([0x15, 0x01])
                response = h.read(7)
                
                if response[0] == 0x16:
                    if response[2] == 5:  # Success
                        responsive_addresses.append(addr)
                        print(f"  ✓ Address 0x{addr:02X} - RESPONSIVE")
                    elif response[2] == 6:  # NACK
                        print(f"  - Address 0x{addr:02X} - NACK (device present but not responding)")
                
                time.sleep(0.01)  # 10ms delay between tests
                
            except Exception as e:
                print(f"  ✗ Address 0x{addr:02X} - Error: {e}")
        
        print(f"\nFound {len(responsive_addresses)} responsive devices")
        
        # Test 2: Specific SI5351A addresses
        print("\n=== Test 2: SI5351A Specific Addresses ===")
        si5351a_addresses = [0x60, 0x61]
        
        for addr in si5351a_addresses:
            print(f"\nTesting SI5351A address 0x{addr:02X}:")
            
            try:
                # Try to read device ID register (0x00)
                print(f"  Attempting to read Device ID register...")
                h.write([0x11, addr<<1, 0x00, 0x01, 0x01, 0x00])
                
                for attempt in range(10):
                    h.write([0x15, 0x01])
                    response = h.read(7)
                    
                    if response[0] == 0x16:
                        if response[2] == 5:  # Success
                            h.write([0x12, 0x00, 0x01])
                            data_response = h.read(4)
                            device_id = data_response[3]
                            print(f"  ✓ SUCCESS! Device ID: 0x{device_id:02X}")
                            print(f"  ✓ SI5351A found at address 0x{addr:02X}")
                            break
                        elif response[2] == 6:  # NACK
                            print(f"  - NACK received (device present but not SI5351A)")
                            break
                    
                    time.sleep(0.01)
                else:
                    print(f"  ✗ No response after 10 attempts")
                    
            except Exception as e:
                print(f"  ✗ Error: {e}")
        
        # Test 3: Check I2C bus state
        print("\n=== Test 3: I2C Bus State ===")
        try:
            # Reset I2C bus
            print("  Resetting I2C bus...")
            h.send_feature_report([0x01, 0x01])
            time.sleep(0.1)
            
            # Check if bus is free
            print("  Checking bus state...")
            h.write([0x15, 0x01])
            response = h.read(7)
            
            if response[0] == 0x16:
                print("  ✓ I2C bus appears to be functional")
            else:
                print("  ✗ I2C bus may have issues")
                
        except Exception as e:
            print(f"  ✗ Bus state check failed: {e}")
        
        h.close()
        
        # Summary and recommendations
        print("\n=== Summary and Recommendations ===")
        if len(responsive_addresses) == 0:
            print("✗ No I2C devices found on the bus")
            print("\nPossible issues:")
            print("1. Check physical connections (SDA, SCL, VCC, GND)")
            print("2. Verify pull-up resistors (4.7kΩ to 3.3V)")
            print("3. Confirm power supply voltage (3.3V)")
            print("4. Check if SI5351A is properly powered")
            print("5. Verify CP2112 is not sharing bus with other devices")
        else:
            print(f"✓ Found {len(responsive_addresses)} I2C devices")
            print("  Responsive addresses:", [f"0x{addr:02X}" for addr in responsive_addresses])
            
        if 0x60 not in responsive_addresses and 0x61 not in responsive_addresses:
            print("\n✗ SI5351A not found at expected addresses (0x60, 0x61)")
            print("  - Check SI5351A power supply")
            print("  - Verify crystal oscillator connection")
            print("  - Confirm I2C address selection (ADDR pin)")
        
    except Exception as e:
        print(f"✗ Failed to initialize CP2112: {e}")
        print("  - Check USB connection")
        print("  - Verify CP2112 drivers are installed")
        print("  - Try different USB port")

if __name__ == "__main__":
    i2c_diagnostic() 