#!/usr/bin/env python
"""
Script to add initial WiFi networks to the database.
Run this after migration to populate the WiFi networks table.
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenwatts.settings')
django.setup()

from greenwatts.adminpanel.models import WiFiNetwork

def add_initial_networks():
    """Add initial WiFi networks with priorities"""
    
    networks = [
        {"ssid": "greenwatts", "password": "greenwatts123", "priority": 1},
        {"ssid": "PLDTLANG", "password": "Successed@123", "priority": 2},
        {"ssid": "STUDENT-CONNECT", "password": "IloveUSTP!", "priority": 3},
        {"ssid": "SobaMask", "password": "12345678", "priority": 4},
    ]
    
    for network_data in networks:
        wifi_network, created = WiFiNetwork.objects.get_or_create(
            ssid=network_data["ssid"],
            defaults={
                "password": network_data["password"],
                "priority": network_data["priority"],
                "is_active": True
            }
        )
        
        if created:
            print(f"[+] Added WiFi network: {network_data['ssid']} (Priority: {network_data['priority']})")
        else:
            print(f"[-] WiFi network already exists: {network_data['ssid']}")
    
    print(f"\nTotal active WiFi networks: {WiFiNetwork.objects.filter(is_active=True).count()}")

if __name__ == "__main__":
    add_initial_networks()