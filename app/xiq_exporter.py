#!/usr/bin/env python3
import logging
import os
import inspect
import sys
import json
import requests
from typing import Any
import pandas as pd
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir) 
from requests.exceptions import HTTPError
from app.mapImportLogger import logger

logger = logging.getLogger('MapImporter.xiq_exporter')

PATH = current_dir
DEFAULT_PAGE_SIZE = 100

class APICallFailedException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class APICallRetryException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class XIQ:
    def __init__(self, user_name, password):
        self.URL = "https://api.extremecloudiq.com"
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        self.totalretries = 5
        self.locationTree_df = pd.DataFrame(columns = ['id', 'name', 'type', 'parent'])
        try:
            self.__getAccessToken(user_name, password)
        except APICallFailedException as e:
            print(e)
            sys.exit(1)
        except HTTPError as e:
           print(e)
           sys.exit(1)
        except:
            log_msg = "Unknown Error: Failed to generate token for XIQ"
            logger.error(log_msg)
            print(log_msg)
            sys.exit(1)

    #API CALLS
    def __setup_get_api_call(self, info, url, params=None):
        success = 0
        last_error = None
        for count in range(1, self.totalretries+1):
            try:
                response = self.__get_api_call(url=url, params=params)
            except APICallRetryException as e:
                print(f"API to {info} failed attempt {count} of {self.totalretries} with {e}")
                last_error = e
            except Exception as e:
                print(f"API to {info} failed with {e}")
                raise
            else:
                success = 1
                break
        if success != 1:
            log_msg = f"API failed to {info}. Cannot continue to import - {last_error}"
            logger.error(log_msg)
            raise APICallFailedException(log_msg)
        if 'error' in response:
            if response['error_message']:
                log_msg = (f"API failed to {info} with reason: Status Code {response['error_id']}: {response['error_message']}")
                logger.error(log_msg)
                raise APICallFailedException(log_msg)
        return response
        
    def __setup_post_api_call(self, info, url, payload):
        success = 0
        last_error = None
        for count in range(1, self.totalretries+1):
            try:
                response = self.__post_api_call(url=url, payload=payload)
            except APICallRetryException as e:
                print(f"API to {info} failed attempt {count} of {self.totalretries} with {e}")
                last_error = e
            except Exception as e:
                print(f"API to {info} failed with {e}")
                raise
            else:
                success = 1
                break
        if success != 1:
            log_msg = f"API failed to {info}. Cannot continue to import - {last_error}"
            logger.error(log_msg)
            raise APICallFailedException(log_msg)
        if 'error' in response:
            if response['error_message']:
                log_msg = (f"API Failed {info} with reason: Status Code {response['error_id']}: {response['error_message']}")
                logger.error(log_msg)
                raise APICallFailedException(log_msg)
        return response
    
    def __setup_put_api_call(self, info, url, payload=''):
        success = 0
        last_error = None
        for count in range(1, self.totalretries+1):
            try:
                if payload:
                    self.__put_api_call(url=url, payload=payload)
                else:
                    self.__put_api_call(url=url)
            except APICallRetryException as e:
                print(f"API to {info} failed attempt {count} of {self.totalretries} with {e}")
                last_error = e
            except Exception as e:
                print(f"API to {info} failed with {e}")
                raise
            else:
                success = 1
                break
        if success != 1:
            log_msg = f"API failed to {info}. Cannot continue to import - {last_error}"
            logger.error(log_msg)
            raise APICallFailedException(log_msg)
        
        return 'Success'

    def __paged(self, info: str, url: str, params: dict[str, Any] | None = None, limit: int = DEFAULT_PAGE_SIZE):
        page = 1
        while True:
            merged = dict(params or {})
            merged["page"] = page
            merged["limit"] = limit
            try:
                body = self.__setup_get_api_call(info, url, params=merged)
            except APICallFailedException as e:
                print(e)
                print("Script is exiting...")
                sys.exit(1)
            if not isinstance(body, dict):
                # non-paginated endpoint answered with a bare list
                yield from body or []
                return
            data = body.get("data") or []
            yield from data
            total_pages = body.get("total_pages") or 0
            if page >= total_pages or not data:
                return
            page += 1
            
    def __get_api_call(self, url, params=None):
        try:
            response = requests.get(url, headers= self.headers, params=params)
        except HTTPError as http_err:
            logger.error(f'HTTP error occurred: {http_err} - on API {url}')
            raise APICallRetryException(f'HTTP error occurred: {http_err}') 
        if response is None:
            log_msg = "ERROR: No response received from XIQ!"
            logger.error(log_msg)
            raise APICallRetryException(log_msg)
        if response.status_code != 200:
            log_msg = f"Error - HTTP Status Code: {str(response.status_code)} - check logs for details"
            logger.error(f"{log_msg}")
            logger.warning(f"\t\t{response.text}")
            raise APICallRetryException(log_msg)  
        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.error(f"Unable to parse json data - {url} - HTTP Status Code: {str(response.status_code)}")
            raise APICallRetryException("Unable to parse the data from json, script cannot proceed")
        return data

    def __post_api_call(self, url, payload):
        try:
            response = requests.post(url, headers= self.headers, data=payload)
        except HTTPError as http_err:
            logger.error(f'HTTP error occurred: {http_err} - on API {url}')
            raise APICallRetryException(f'HTTP error occurred: {http_err}') 
        if response is None:
            log_msg = "ERROR: No response received from XIQ!"
            logger.error(log_msg)
            raise APICallRetryException(log_msg)
        if response.status_code == 202:
            return "Success"
        elif response.status_code != 200:
            log_msg = f"Error - HTTP Status Code: {str(response.status_code)}"
            logger.error(f"{log_msg}")
            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.warning(f"\t\t{response.text}")
            else:
                if 'error_message' in data:
                    logger.warning(f"\t\t{data['error_message']}")
                    # Don't retry on authentication errors (401)
                    if response.status_code == 401:
                        raise APICallFailedException(data['error_message'])
                    raise APICallRetryException(data['error_message'])
            # Don't retry on authentication errors (401)
            if response.status_code == 401:
                raise APICallFailedException(log_msg)
            raise APICallRetryException(log_msg)
        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.error(f"Unable to parse json data - {url} - HTTP Status Code: {str(response.status_code)}")
            raise APICallRetryException("Unable to parse the data from json, script cannot proceed")
        return data
    
    def __put_api_call(self, url, payload=''):
        try:
            if payload:
                response = requests.put(url, headers= self.headers, data=payload)
            else:
                response = requests.put(url, headers= self.headers)
        except HTTPError as http_err:
            logger.error(f'HTTP error occurred: {http_err} - on API {url}')
            raise APICallRetryException(f'HTTP error occurred: {http_err}') 
        if response is None:
            log_msg = "ERROR: No response received from XIQ!"
            logger.error(log_msg)
            raise APICallRetryException(log_msg)
        if response.status_code != 200:
            log_msg = f"Error - HTTP Status Code: {str(response.status_code)}"
            logger.error(f"{log_msg}")
            logger.warning(f"\t\t{response}")
            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.warning(f"\t\t{response.text}")
            else:
                if 'error_message' in data:
                    logger.warning(f"\t\t{data['error_message']}")
                    raise APICallRetryException(data['error_message'])
                raise APICallRetryException(log_msg)
        return response.status_code


    def __getAccessToken(self, user_name, password):
        info = "get XIQ token"
        success = 0
        url = self.URL + "/login"
        payload = json.dumps({"username": user_name, "password": password})
        try:
            data = self.__setup_post_api_call(info=info,url=url,payload=payload)
        except APICallFailedException as e:
            print(e)
            print("failed to get XIQ token. Cannot continue to import")
            print("Script is exiting...")
            sys.exit(1) 
       
        if "access_token" in data:
            #print("Logged in and Got access token: " + data["access_token"])
            self.headers["Authorization"] = "Bearer " + data["access_token"]
            return 0

        else:
            log_msg = "Unknown Error: Unable to gain access token for XIQ"
            logger.warning(log_msg)
            raise APICallFailedException(log_msg)
    
    # EXTERNAL ACCOUNTS
    def __getVIQInfo(self):
        info="get current VIQ name"
        url = f"{self.URL}/account/home"
        try:
            data = self.__setup_get_api_call(info=info, url=url)
        except APICallFailedException as e:
            print(f"API to {info} failed with {e}")
            raise
        except Exception as e:
            print(f"API to {info} failed with unknown API error: {e}")
            raise
        else:
            self.viqName = data['name']
            self.viqID = data['id']


    ## EXTERNAL FUNCTION

    #ACCOUNT SWITCH
    def selectManagedAccount(self):
        self.__getVIQInfo()
        info="gather accessible external XIQ accounts"
        url = f"{self.URL}/account/external"
        data = self.__setup_get_api_call(info=info, url=url)
        return(data, self.viqName)


    def switchAccount(self, viqID, viqName):
        info=f"switch to external account {viqName}"
        success = 0
        url = f"{self.URL}/account/:switch?id={viqID}"
        payload = ''
        try:
            data = self.__setup_post_api_call(info=info, url=url, payload=payload)
        except APICallFailedException as e:
            print(f"API to {info} failed with {e}")
            print("Script is exiting...")
            sys.exit(1)
        if "access_token" in data:
            self.headers["Authorization"] = "Bearer " + data["access_token"]
            self.__getVIQInfo()
            if viqName != self.viqName:
                logger.error(f"Failed to switch external accounts. Script attempted to switch to {viqName} but is still in {self.viqName}")
                print("Failed to switch to external account!!")
                print("Script is exiting...")
                sys.exit(1)
            return 0

        else:
            log_msg = "Unknown Error: Unable to gain access token for XIQ"
            logger.warning(log_msg)
            logger.warning(data)
            print("Script is exiting...")
            sys.exit(1) 
        

    # LOCATIONS

    # Gather Buildings
    def gatherBuildings(self):
        info=f"gather list of buildings"
        url = f"{self.URL}/locations/building"
        xiq_building_data = self.__paged(info, url)
        data = [{'id': b['id'], 'name': b['name'], 'parent': b['parent_id']} for b in xiq_building_data]
        building_df = pd.DataFrame(data)
        return building_df
    
    # Gather Floors
    def gatherFloors(self, building_id):
        info=f"gather list of floors for building {building_id}"
        url = f"{self.URL}/locations/tree"
        params = {'parentId': building_id, "expandChildren": "true"}
        try:
            xiq_floor_data = self.__setup_get_api_call(info, url, params=params)
        except APICallFailedException as e:
            print(e)
            print("Script is exiting...")
            sys.exit(1)
        floor_data = [{'id': f['id'], 'name': f['name'], 'parent': f['parent_id']} for f in xiq_floor_data if f['type'] == 'FLOOR']
        if not floor_data:
            print(f"No floors found for building {building_id}")
            print("Script is exiting...")
            sys.exit(1)
        floor_df = pd.DataFrame(floor_data)
        return floor_df
   
    #APS
    def gatherAPsBySerial(self, serial_numbers):
        info=f"gather list of APs for serial numbers {serial_numbers}"
        url = f"{self.URL}/devices"
        params = {'sns': serial_numbers, "views": "FULL"}
        xiq_ap_data = self.__paged(info, url, params=params, limit=100)
        
        ap_data = [{'id': a['id'], 'name': a['hostname'], 'serial_number': a['serial_number'].strip().lower(), 'model': a['product_type'], 'location_id': a.get('location_id', '')} for a in xiq_ap_data if a['device_function'] == 'AP']
        if not ap_data:
            print(f"No APs found for serial numbers {serial_numbers}")
            print("Script is exiting...")
            sys.exit(1)
        for ap in ap_data:
            if 'location_id' in ap and ap['location_id']:
                ap_id = ap['id']
                url = f"{self.URL}/devices/{ap_id}/location"
                try:
                    response = self.__setup_get_api_call(info, url)
                except APICallFailedException as e:
                    print(e)
                    print("Script is exiting...")
                    sys.exit(1)
                if 'x' in response and 'y' in response:
                    ap['x'] = response['x']
                    ap['y'] = response['y']
                else:
                    ap['x'] = None
                    ap['y'] = None
                if 'latitude' in response and 'longitude' in response:
                    ap['latitude'] = response['latitude']
                    ap['longitude'] = response['longitude']
                else:
                    ap['latitude'] = 0
                    ap['longitude'] = 0
            else:
                ap['x'] = None
                ap['y'] = None
                ap['latitude'] = 0
                ap['longitude'] = 0
        ap_df = pd.DataFrame(ap_data)
        return ap_df
    

    def updateAPLocation(self, ap_id, ap_name, ap_data):
        info=f"update AP location for {ap_name}"
        url = f"{self.URL}/devices/{ap_id}/location"
        payload = json.dumps(ap_data)
        response = self.__setup_put_api_call(info,url,payload)
        return response
    
