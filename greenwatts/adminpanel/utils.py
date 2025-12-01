import random

def get_random_energy_tip():
    """
    Returns a random energy saving tip for display on admin pages.
    """
    energy_tips = [
        "On warm days, setting a programmable thermostat to a higher setting when you are not at home can help reduce your energy costs by approximately 10 percent.",
        "LED bulbs use up to 80% less energy than traditional incandescent bulbs and last 25 times longer.",
        "Unplugging electronics when not in use can save up to 10% on your electricity bill, as many devices draw power even when turned off.",
        "Using a power strip makes it easy to turn off multiple devices at once, preventing phantom energy drain.",
        "Setting your water heater to 120°F (49°C) can reduce energy consumption by 6-10% compared to higher temperatures.",
        "Air-drying clothes instead of using a dryer can save significant energy, especially during warmer months.",
        "Closing blinds and curtains during hot days can reduce cooling costs by up to 20%.",
        "Regular maintenance of HVAC systems, including changing filters, can improve efficiency by 5-15%.",
        "Using ceiling fans allows you to raise the thermostat by 4°F without reducing comfort, saving energy.",
        "Energy-efficient appliances with ENERGY STAR ratings use 10-50% less energy than standard models.",
        "Sealing air leaks around windows and doors can reduce heating and cooling costs by up to 15%.",
        "Using cold water for washing clothes can save up to 90% of the energy used for laundry.",
        "Installing a programmable or smart thermostat can save up to 10% on heating and cooling costs.",
        "Turning off lights when leaving a room is a simple way to reduce energy consumption immediately.",
        "Using natural light during the day reduces the need for artificial lighting and can improve productivity.",
        "Insulating your water heater and pipes can reduce heat loss and save 7-16% on water heating costs.",
        "Running dishwashers and washing machines with full loads maximizes energy efficiency per item cleaned.",
        "Using laptop computers instead of desktop computers can reduce energy consumption by up to 80%.",
        "Installing motion sensors for lighting in less frequently used areas prevents lights from being left on unnecessarily.",
        "Upgrading to double-pane windows can reduce energy loss through windows by up to 50%."
    ]
    
    return random.choice(energy_tips)