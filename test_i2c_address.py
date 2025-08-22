#!/usr/bin/env python3
"""
Test script to find the correct I2C address for SI5351A device
"""

import hid
import time

def test_i2c_addresses():
    """Test both possible I2C addresses for SI5351A"""
    
    # Initialize CP2112
    try:
        h = hid.device()
        h.open(0x10C4, 0xEA90, None)
        
        print("Manufacturer: %s" % h.get_manufacturer_string())
        print("Product: %s" % h.get_product_string())
        print("Serial No: %s" % h.get_serial_number_string())
        
        # Set I2C configuration
        print("Set SMB Configuration - 400kHz")
        h.send_feature_report([0x06, 0x00, 0x01, 0x86, 0xA0, 0x02, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x01, 0x00, 0x0F])
        
        # Test addresses 0x60 and 0x61
        addresses = [0x60, 0x61]
        
        for addr in addresses:
            print(f"\nTesting I2C address 0x{addr:02X}...")
            
            try:
                # Try to read device ID register (0x00)
                h.write([0x11, addr<<1, 0x00, 0x01, 0x01, 0x00])
                
                for k in range(20):
                    h.write([0x15, 0x01])
                    response = h.read(7)
                    if (response[0] == 0x16) and (response[2] == 5):
                        h.write([0x12, 0x00, 0x01])
                        response = h.read(4)
                        device_id = response[3]
                        print(f"  ✓ Device ID: 0x{device_id:02X}")
                        print(f"  ✓ Address 0x{addr:02X} is VALID")
                        break
                    time.sleep(0.001)
                else:
                    print(f"  ✗ Address 0x{addr:02X} - No response")
                    
            except Exception as e:
                print(f"  ✗ Address 0x{addr:02X} - Error: {e}")
        
        h.close()
        
    except Exception as e:
        print(f"Error initializing CP2112: {e}")

if __name__ == "__main__":
    test_i2c_addresses() 