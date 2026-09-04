#!/usr/bin/env python3
import logging
import argparse
import re
import sys
import os
import inspect
import getpass
import pandas as pd
import numpy as np
from app.Ekahau_importer import Ekahau
from app.ap_csv_importer import apSerialCSV
from app.mapImportLogger import logger
from app.xiq_exporter import XIQ, APICallFailedException
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

        
parser = argparse.ArgumentParser()
parser.add_argument('--external',action="store_true", help="Optional - adds External Account selection, to create floorplans and APs on external VIQ")
parser.add_argument('--csv', type=str, help="Optional - Allows to import a CSV file that will match AP names to serial numbers") 
args = parser.parse_args()

PATH = current_dir

if sys.stdout.isatty():
    # Git Shell Coloring - https://gist.github.com/vratiu/9780109
    RED   = "\033[1;31m"  
    BLUE  = "\033[1;34m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    RESET = "\033[0;0m"
else:
    RED = BLUE = GREEN = YELLOW = RESET = ""

def yesNoLoop(question):
    validResponse = False
    while validResponse != True:
        response = input(f"{question} (y/n) ").lower()
        if response =='n' or response == 'no':
            response = 'n'
            validResponse = True
        elif response == 'y' or response == 'yes':
            response = 'y'
            validResponse = True
        elif response == 'q' or response == 'quit':
            sys.stdout.write(RED)
            sys.stdout.write("script is exiting....\n")
            sys.stdout.write(RESET)
            sys.exit(1)
    return response

def selectFromDataFrame(df, prompt, extra_options=None):
    validResponse = False
    while validResponse != True:
        print(f"\n{prompt}")
        count = 0
        for df_id, info in df.iterrows():
            print(f"   {df_id}. {info['name']}")
            count = len(df) - 1
        if extra_options:
            for option in extra_options:
                count += 1
                print(f"   {count}. {option}")
        selection = input(f"Please enter 0 - {count}: ")
        try:
            selection = int(selection)
        except ValueError:
            sys.stdout.write(YELLOW)
            sys.stdout.write("Please enter a valid response!!\n")
            sys.stdout.write(RESET)
            continue
        if 0 <= selection <= count:
            validResponse = True
    return selection

def main():
    ## EKAHAU IMPORT
    filename = str(input("Please enter the Ekahau File: ")).strip()
    filename = filename.strip('\'"')          # drag-and-drop sometimes wraps the whole path in quotes
    filename = re.sub(r'\\(.)', r'\1', filename)  # undo backslash-escaping of any character

    print("When this file was uploaded to XIQ was it imported using the native Ekahau import in XIQ or Extreme Platform One? Or was it imported using the XIQ_Ekahau_Importer script?")
    validResponse = False
    while validResponse != True:
        print("   1. Native Ekahau Import")
        print("   2. XIQ_Ekahau_Importer Script")
        response = input("Enter your choice (1 or 2): ").strip()
        if response == "1":
            XiqNativeImport = True
            validResponse = True
        elif response == "2":
            XiqNativeImport = False
            validResponse = True
        else:
            print("Invalid choice. Please enter 1 or 2.")

    saveImages = False
    print("Gathering Ekahau Data.... ", end='')
    sys.stdout.flush()
    x = Ekahau(filename,XiqNativeImport)
    try:
        rawData = x.exportFile()
    except ValueError as e:
        print("Failed")
        sys.stdout.write(YELLOW)
        sys.stdout.write(str(e) +'\n')
        sys.stdout.write(RED)
        sys.stdout.write("script is exiting....\n")
        sys.stdout.write(RESET)
        sys.exit(1)
    except Exception as e:
        log_msg = "Unknown Error opening and exporting Ekahau data: " + str(e)
        print("Failed")
        print(log_msg)
        logger.error(log_msg)
        sys.exit(1)
    print("Complete\n")


    ## CSV AP MAPPER
    if args.csv:
        print("Gathering Serial Numbers from CSV file.... ", end='')
        sys.stdout.flush()
        filename = args.csv
        x = apSerialCSV(filename, rawData['aps'])
        try:
            rawData['aps'], unmatched_ap_info_ap, unmatched_csv_ap = x.getSerialNumbers()
        except ValueError as e:
            sys.stdout.write(RED)
            sys.stdout.write(str(e) +'\n')
            sys.stdout.write("script is exiting....\n")
            sys.stdout.write(RESET)
            logger.error(str(e))
            sys.exit(1)
        except Exception as e:
            log_msg = "Unknown Error opening and exporting CSV data: " + str(e)
            sys.stdout.write(RED)
            sys.stdout.write(log_msg+"\n")
            sys.stdout.write("script is exiting....\n")
            sys.stdout.write(RESET)
            logger.error(log_msg)
            sys.exit(1)
        print("Complete\n")
        if unmatched_ap_info_ap:
            print("These APs were not found in CSV\n  ", end='')
            print(*unmatched_ap_info_ap, sep='\n  ')
            logger.warning("These APs were not found in the CSV file: " + ",".join(unmatched_ap_info_ap))
        if unmatched_csv_ap:
            print("These APs were in the CSV but did not match the name of any AP\n  ", end='')
            print(*unmatched_csv_ap, sep='\n  ')
            logger.warning("These APs were in the CSV file but did not match the name of any AP in Ekahau: " + ",".join(unmatched_csv_ap))

    ## XIQ EXPORT

    print("Enter your XIQ login credentials")
    username = input("Email: ")
    password = getpass.getpass("Password: ")

    x = XIQ(username,password)
    if args.external:
        try:
            accounts, viqName = x.selectManagedAccount()
        except APICallFailedException as e:
            print(f"Failed to collect managed accounts: {e}")
            response = yesNoLoop("Would you like to continue to import data to your main account? (y/n)")
            if response == 'n':
                sys.stdout.write("Thanks. ")
                sys.stdout.write(RED)
                sys.stdout.write("Script is exiting....\n")
                sys.stdout.write(RESET)
                sys.exit(1)
        except Exception as e:
            print(f"Failed to collect managed accounts: {e}")
            response = yesNoLoop("Would you like to continue to import data to your main account? (y/n)")
            if response == 'n':
                sys.stdout.write("Thanks. ")
                sys.stdout.write(RED)
                sys.stdout.write("Script is exiting....\n")
                sys.stdout.write(RESET)
                sys.exit(1)
        if accounts == 1:
            response = yesNoLoop("No External accounts found. Would you like to import data to your network? (y/n)")
            if response =='n':
                sys.stdout.write("Thanks. ")
                sys.stdout.write(RED)
                sys.stdout.write("Script is exiting....\n")
                sys.stdout.write(RESET)
                sys.exit(1)
        elif accounts:
            accounts_df = pd.DataFrame(accounts)
            selection = selectFromDataFrame(accounts_df, "\nWhich VIQ would you like to import the floor plan and APs too?", extra_options=[f"{viqName} (This is Your main account)"])
            if selection != len(accounts_df): 
                newViqID = (accounts_df.loc[int(selection),'id'])
                newViqName = (accounts_df.loc[int(selection),'name'])
                x.switchAccount(newViqID, newViqName)
            
    xiq_building_exist = False
    ekahau_building_exists = False
    xiq_building_id = None

    building_df = x.gatherBuildings()

    # Check if building in Ekahau is defined
    if rawData['building']:
        for building in rawData['building']:
            #if not (lambda x: x['associated_building_id'] == building['building_id'], rawData['floors']):
            if not any(d['associated_building_id'] == building['building_id'] for d in rawData['floors']):
                log_msg = (f"no floors were found for building {building['name']}. Skipping creation of building")
                logger.info(log_msg)
                continue
            ekahau_building_exists = True
            # Check if building exists in XIQ
            if building['name'] in building_df['name'].unique():
                response = yesNoLoop(f"{building['name']} was found in XIQ. Would you like to use this building?")
                if response == 'y':
                    xiq_building_exist = True
                    xiq_building_id = building_df.loc[building_df['name'] == building['name'], 'id'].values[0]
                    xiq_building_name = building['name']

    ## If not in Ekahau or no match found in XIQ, select from list of existing buildings
    if ekahau_building_exists == False or xiq_building_exist == False:
        selection = selectFromDataFrame(building_df, "\nWhich Building would you like to check AP locations for?")
        xiq_building_id = (building_df.loc[int(selection),'id'])
        xiq_building_name = (building_df.loc[int(selection),'name'])
    print(f"AP locations will be validated for Building {xiq_building_name}")

    # Check floors of building
    floors_df = x.gatherFloors(xiq_building_id)

    for floor in rawData['floors']:
        print("Checking floor " + floor['name'] + ".... ")
        sys.stdout.flush()
        floor_name = floor['name']
        if floor_name in floors_df['name'].unique():
            floor['xiq_floor_id'] = floors_df.loc[floors_df['name'] == floor_name, 'id'].values[0]
            log_msg = (f"Floor {floor_name} was found in XIQ. Will check APs to this floor")
            logger.info(log_msg)
        else:
            log_msg = (f"Floor {floor_name} was not found in XIQ under building {xiq_building_name}.")
            logger.warning(log_msg)
            sys.stdout.write(YELLOW)
            sys.stdout.write("\n"+log_msg + '\n')
            sys.stdout.write("Please make sure the floor name in the Ekahau project matches the floor name in XIQ and try again.")
            sys.stdout.write("Script is exiting...")
            sys.stdout.write(RESET)
            sys.exit(1)

    ## Get new locations of APs
    # ADD APS TO FLOORS
    ek_floor_df = pd.DataFrame(rawData['floors'])
    ek_ap_df = pd.DataFrame(rawData['aps'])

    listOfFloors = list(ek_ap_df['location_id'].unique())
    for floor_id in listOfFloors:
        filt = ek_floor_df['floor_id'] == floor_id
        if not ek_floor_df.loc[filt].empty:
            xiq_id = ek_floor_df.loc[filt,'xiq_floor_id'].values[0]
            ek_ap_df = ek_ap_df.replace({'location_id':{floor_id : str(xiq_id)}})
        else:
            log_msg = f"AP location references floor_id {floor_id}, which was not found in the Ekahau floor data."
            logger.error(log_msg)
            sys.stdout.write(RED)
            sys.stdout.write(log_msg + "\n")
            sys.stdout.write("script is exiting....\n")
            sys.stdout.write(RESET)
            sys.exit(1)

    ek_ap_df['sn'] = ek_ap_df['sn'].str.strip().str.lower().replace('', np.nan)
    duplicateSN = ek_ap_df['sn'].dropna().duplicated().any()
    if duplicateSN:
        log_msg = ("\nMultiple APs have the same serial numbers. Please fix and try again.")
        logger.warning(log_msg)
        sys.stdout.write(RED)
        sys.stdout.write(log_msg + '\n')
        sys.stdout.write("script is exiting....")
        sys.stdout.write(RESET)
        sys.exit(1)
    nanValues = ek_ap_df[ek_ap_df['sn'].isna()]
    ek_ap_df.dropna(subset=["sn"], inplace=True)
    # End script if no APs have serial numbers
    if nanValues.name.size > 0 and len(ek_ap_df['sn'].tolist()) == 0:
        log_msg = ("\nSerial numbers were not found for any AP. Please check to make sure they are added correctly and try again.")
        logger.warning(log_msg)
        sys.stdout.write(YELLOW)
        sys.stdout.write("\n"+log_msg + '\n')
        print("script is exiting....")
        sys.stdout.write(RESET)
        sys.stdout.flush()
        sys.exit(1)
    # remove APs that do not have serial numbers
    elif nanValues.name.size > 0:
        print("\nSerial numbers were not found for these APs. Please correct and run the script again if you would like to add them.\n  ", end='')
        print(*nanValues.name.values, sep = "\n  ")
        logger.info("Serial numbers were not found for these APs: " + ",".join(nanValues.name.values))

    ## Get existing locations of APs based on serial numbers from XIQ
    ap_df = x.gatherAPsBySerial(ek_ap_df['sn'].tolist())

    ## Check for APs without locations
    ap_df['location_id'] = ap_df['location_id'].replace('', np.nan)
    nanValues = ap_df[ap_df['location_id'].isna()]
    ap_df.dropna(subset=["location_id"], inplace=True)

    ## Map out changes for approval
    update_list = []
    for ap_id, ap_info in ek_ap_df.iterrows():
        filt = ap_df['serial_number'] == ap_info['sn']
        if not ap_df.loc[filt].empty:
            xiq_location_id = (ap_df.loc[filt,'location_id'].values[0])
            location_changed = str(ap_info['location_id']) != str(xiq_location_id)
            xy_changed = (not np.isclose(ap_info['x'], ap_df.loc[filt,'x'].values[0], atol=1e-6)
                          or not np.isclose(ap_info['y'], ap_df.loc[filt,'y'].values[0], atol=1e-6))
            if location_changed:
                print(f"AP {ap_info['name']} was moved from {xiq_location_id} to {ap_info['location_id']}")
            if xy_changed:
                print(f"AP {ap_info['name']} was moved from ({ap_df.loc[filt,'x'].values[0]}, {ap_df.loc[filt,'y'].values[0]}) to ({ap_info['x']}, {ap_info['y']})")
            if location_changed or xy_changed:
                update_list.append({
                    'id': ap_df.loc[filt,'id'].values[0], 'name': ap_info['name'], 'serial_number': ap_info['sn'],
                    'location_id': ap_info['location_id'], 'x': ap_info['x'], 'y': ap_info['y'],
                    'latitude': ap_df.loc[filt,'latitude'].values[0], 'longitude': ap_df.loc[filt,'longitude'].values[0],
                })

    # List out APs that will be updated
    if update_list:
        print("\nThe following APs will be updated:")
        for ap_update_location in update_list:
            print(f"   {ap_update_location['name']} - Serial Number: {ap_update_location['serial_number']} - New Location ID: {ap_update_location['location_id']} - New Coordinates: ({ap_update_location['x']}, {ap_update_location['y']})")
        response = yesNoLoop("Would you like to proceed with the updates?")
        if response == 'n':
            sys.stdout.write(RED)
            sys.stdout.write("script is exiting....\n")
            sys.stdout.write(RESET)
            sys.exit(1)

        success_count = 0
        failure_list = []
        print("\nUpdating AP locations in XIQ.... ", end='')
        sys.stdout.flush()
        for ap_update_location in update_list:
        
            ap_data = {
                'location_id': int(ap_update_location['location_id']),
                'x': float(ap_update_location['x']),
                'y': float(ap_update_location['y']),
                'latitude': float(ap_update_location['latitude']),
                'longitude': float(ap_update_location['longitude']),
            }
            try:
                x.updateAPLocation(ap_update_location['id'], ap_update_location['name'], ap_data)
                success_count += 1
                logger.info(f"Updated AP {ap_update_location['name']} (Serial Number: {ap_update_location['serial_number']}) to location_id {ap_update_location['location_id']}, x={ap_update_location['x']}, y={ap_update_location['y']}")
            except APICallFailedException as e:
                 failure_list.append(ap_update_location['name'])
                 log_msg = f"Failed to update AP {ap_update_location['name']} with Serial Number {ap_update_location['serial_number']}: {e}"
                 logger.error(log_msg)
                 print(log_msg)
                 continue

        log_msg = f"{success_count} of {len(update_list)} APs updated successfully."
        print(f"\n{log_msg}")
        logger.info(log_msg)
        if failure_list:
            log_msg = "These APs failed to update: " + ", ".join(failure_list)
            logger.warning(log_msg)
            sys.stdout.write(YELLOW)
            print("These APs failed to update:\n  " + "\n  ".join(failure_list))
            sys.stdout.write(RESET)



if __name__ == '__main__':
	main()