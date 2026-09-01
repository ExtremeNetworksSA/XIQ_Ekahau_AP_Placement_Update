#!/usr/bin/env python3
from math import floor
from zipfile import ZipFile
import json
import logging
import os
import inspect
import shutil
import sys
import cv2
import pandas as pd
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir) 
from app.mapImportLogger import logger

logger = logging.getLogger('MapImporter.EkahauImporter')

PATH = current_dir

class Ekahau:
    def __init__(self, filename, XiqNativeImport): 
        self.filename = filename
        self.x_scale = 1
        self.y_scale = 1
        if XiqNativeImport:
            self.cropRotateSupport = False
            self.serialInTags = True
        else:
            self.cropRotateSupport = True
            self.serialInTags = False

        directory = PATH + '/images'
        if os.path.isdir(directory):
            for f in os.listdir(directory):
                os.remove(os.path.join(directory, f))
        else:
            os.makedirs(directory)
        
        self.projectFolder = f"{PATH}/project"
        if os.path.exists(self.projectFolder) and os.path.isdir(self.projectFolder):
            shutil.rmtree(self.projectFolder)

    def __safe_extractall(self, zip_obj, target_dir):
        target_dir = os.path.realpath(target_dir)
        for member in zip_obj.namelist():
            member_path = os.path.realpath(os.path.join(target_dir, member))
            if not member_path.startswith(target_dir + os.sep):
                raise ValueError(f"Unsafe path in zip file: {member}")
        zip_obj.extractall(target_dir)

    def exportFile(self):
        data = {}
        itemList = ['project', 'buildings', 'floorPlans', 'accessPoints', 'buildingFloors', 'floorTypes', 'images', 'tagKeys']
        self.buildingExists = True
        self.tagKeysExist = True
        # Unzip Ekahau folder in to a created 'project' directory
        try:
            with ZipFile(self.filename, 'r') as zip:
                self.__safe_extractall(zip, self.projectFolder)
        except FileNotFoundError:
            log_msg = f"{self.filename} file does not exist"
            logger.error(log_msg)
            raise ValueError(log_msg)
        except json.JSONDecodeError:
            log_msg = f"{self.filename} file is corrupted, script cannot proceed"
            logger.info(log_msg)
            shutil.rmtree(self.projectFolder)
            raise ValueError(log_msg)
        
        #Check version
        dir_list = os.listdir(self.projectFolder)
        if 'project.xml' in dir_list:
            log_msg = ("Older Ekahau file detected. Please update file using Ekahau 10.x and try again.")
            logger.error(log_msg)
            shutil.rmtree(self.projectFolder)
            raise ValueError(log_msg)
        # Import itemList json files 
        for item in itemList:
            try:
                 with open(f"{self.projectFolder}/{item}.json", 'r') as f:
                    data[item] = json.load(f)
            except FileNotFoundError:
                if item == 'buildings' or item == 'buildingFloors':
                    self.buildingExists = False
                    continue
                elif item == 'tagKeys':
                    self.tagKeysExist = False
                    continue
                else:
                    logger.error(f"{item}.json file does not exist")
                    raise ValueError(f"The {item} details were able to be exported from the Ekahau file")
            except json.JSONDecodeError:
                logger.info(f"{item}.json file is corrupted, script cannot proceed")
                raise ValueError(f"The {item} details from Ekahau are corrupted, script cannot proceed")
        # clean APs:

        ap_data = []
        for ap in data['accessPoints']['accessPoints']:
            if 'location' in ap:
                ap_data.append(ap)
        data['accessPoints']['accessPoints'] = ap_data

        self.project_info = data['project']['project']
        if self.buildingExists:
            self.building_df = pd.DataFrame(data['buildings']['buildings'])
            self.building_df = self.building_df.set_index('id')
        self.floorPlans_df = pd.DataFrame(data['floorPlans']['floorPlans'])
        self.floorPlans_df = self.floorPlans_df.set_index('id')
        self.ap_df = pd.DataFrame(data['accessPoints']['accessPoints'])
        self.ap_df = self.ap_df.set_index('id')
        if self.buildingExists:
            self.buildingFloors_df = pd.DataFrame(data['buildingFloors']['buildingFloors'])
            self.buildingFloors_df = self.buildingFloors_df.set_index('id')
        self.floorTypes_df = pd.DataFrame(data['floorTypes']['floorTypes'])
        self.floorTypes_df = self.floorTypes_df.set_index('id')
        self.images_df = pd.DataFrame(data['images']['images'])
        self.images_df = self.images_df.set_index('id')
        if self.tagKeysExist and self.serialInTags:
            for tag in data['tagKeys']['tagKeys']:
                if tag['key'] == 'serialNumber':
                    self.serialTagId = tag['id']
                    break
            if not hasattr(self, 'serialTagId'):
                log_msg = "Serial Number tag was not found in the Ekahau file."
                logger.warning(log_msg)
                print('\n' + log_msg)
                self.serialInTags = False

        self.__versionCheck()

        self.__processEkahauData()
        shutil.rmtree(current_dir + '/project')
        return self.EkahauData
        
    def __versionCheck(self):
        if 'rotateUpDirection' not in self.floorPlans_df.columns:
            log_msg = "This Ekahau file seems to be prior to version 10.3 so crop and rotation of Floors is not supported with this script."
            logger.warning(log_msg)
            print('\n' + log_msg)
            self.floorPlans_df = self.floorPlans_df.assign(rotateUpDirection = "UP")
            self.floorPlans_df = self.floorPlans_df.assign(cropMinX = 0.0)
            self.floorPlans_df = self.floorPlans_df.assign(cropMinY = 0.0)
            self.floorPlans_df = self.floorPlans_df.assign(cropMaxX = lambda x: x.width)
            self.floorPlans_df = self.floorPlans_df.assign(cropMaxY = lambda x: x.height)


    def __floorImageProcessing(self, imageId, imageType):

        if imageType == 'bitmap':
            filt = self.floorPlans_df['bitmapImageId'] == imageId    
        else:
            filt = self.floorPlans_df['imageId'] == imageId
        rawWidth = int(self.images_df.loc[imageId, 'resolutionWidth'])
        rawHeight = int(self.images_df.loc[imageId, 'resolutionHeight'])
        self.x_scale = rawWidth / int(self.floorPlans_df.loc[filt, 'width'].values[0])
        self.y_scale = rawHeight / int(self.floorPlans_df.loc[filt, 'height'].values[0])

        floorName = self.floorPlans_df.loc[filt, 'name'].values[0]
        imageFormat = (self.images_df.loc[imageId, 'imageFormat'])
        orientation = self.floorPlans_df.loc[filt, 'rotateUpDirection'].values[0]

        
        #if imageFormat == 'JPEG':
        fileExt = 'jpg'
        #elif imageFormat == 'PNG':
        #    fileExt = 'png'
    

        floorplan_name = f"{imageId}.{fileExt}"
        filename = f"{self.projectFolder}/image-{imageId}"
        newfilename = f"{PATH}/images/{floorplan_name}"
        try:
            file_size = os.path.getsize(filename)
        except FileNotFoundError:
            if not os.path.isfile(filename):
                log_msg = f"{filename} file does not exist"
                logger.error(log_msg)
                raise ValueError(log_msg)
            elif not os.path.isdir(PATH + '/images/'):
                log_msg = "The /images/ directory is missing in the /app/ directory."
                logger.error(log_msg)
                raise ValueError(log_msg)
        quality = 75
        if file_size > 24550000:
            quality = 50
        image = cv2.imread(filename)
        if image is None:
            log_msg = f"Script failed to read in file {filename}"
            logger.error(log_msg)
            raise ValueError(log_msg)
            
       
        #Cropping image as necessary
        if self.cropRotateSupport:
            minX=int(int(self.floorPlans_df.loc[filt, 'cropMinX'].values[0]) * self.x_scale)
            minY=int(int(self.floorPlans_df.loc[filt, 'cropMinY'].values[0]) * self.y_scale)
            maxX=int(int(self.floorPlans_df.loc[filt, 'cropMaxX'].values[0]) * self.x_scale)
            maxY=int(int(self.floorPlans_df.loc[filt, 'cropMaxY'].values[0]) * self.y_scale)
            #print(minY,maxY, minX,maxX)
            crop_image = image[minY:maxY, minX:maxX]
        
            #Get width and height of the floorplan
            width = (rawWidth - minX - (rawWidth -maxX)) * self.floorPlans_df.loc[filt, 'metersPerUnit'].values[0]
            height = (rawHeight - minY - (rawHeight -maxY)) * self.floorPlans_df.loc[filt, 'metersPerUnit'].values[0]
            #rotate image and width height of floorplan
            if orientation == "LEFT":
                image = cv2.rotate(crop_image, cv2.ROTATE_90_COUNTERCLOCKWISE)
                width, height = height, width
            elif orientation == "RIGHT":
                image = cv2.rotate(crop_image, cv2.ROTATE_90_CLOCKWISE)
                width, height = height, width
            elif orientation == "DOWN":
                image = cv2.rotate(crop_image, cv2.ROTATE_180) 
            elif orientation == "UP":
                image = crop_image
        else:
            # ignore Ekahau cropping and rotation and just use the raw image
            width = rawWidth * self.floorPlans_df.loc[filt, 'metersPerUnit'].values[0]
            height = rawHeight * self.floorPlans_df.loc[filt, 'metersPerUnit'].values[0]
        

        #write file with crop and rotation if applicable
        write_status = cv2.imwrite(newfilename, image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not write_status:
            log_msg = f"Failed to write {newfilename} after cropping"
            logger.error(log_msg)
            raise ValueError(log_msg)
        
        file_size = os.path.getsize(newfilename)
        if file_size > 10000000:
            floorplan_name = 'FILE_TOO_BIG_' + floorplan_name
        return floorplan_name, width, height

    def __updateAPCoord(self, floor_id, rawX,rawY):
        #get correct x,y coords
        ## If crop rotate support is enabled
        if self.cropRotateSupport:
            minX=int(int(self.floorPlans_df.loc[floor_id, 'cropMinX']) * self.x_scale)
            minY=int(int(self.floorPlans_df.loc[floor_id, 'cropMinY']) * self.y_scale)
            maxX=int(int(self.floorPlans_df.loc[floor_id, 'cropMaxX']) * self.x_scale)
            maxY=int(int(self.floorPlans_df.loc[floor_id, 'cropMaxY']) * self.y_scale)

            metersPerUnit = self.floorPlans_df.loc[floor_id, 'metersPerUnit']
            orientation = self.floorPlans_df.loc[floor_id, 'rotateUpDirection']
            rawX = rawX  * self.x_scale
            rawY = rawY  * self.y_scale

            if orientation == 'UP':
                x = (rawX - minX) * metersPerUnit
                y = (rawY - minY) * metersPerUnit
            elif orientation == "RIGHT":
                y = (rawX - minX) * metersPerUnit
                x = (maxY - rawY) * metersPerUnit
            elif orientation == "LEFT":
                x = (rawY - minY) * metersPerUnit
                y = (maxX - rawX) * metersPerUnit
            elif orientation == "DOWN":
                x = (maxX - rawX) * metersPerUnit
                y = (maxY - rawY) * metersPerUnit
        ## If crop rotate support is disabled - ie native XIQ import
        else:
            minX= 0
            minY= 0
            maxX=int(self.floorPlans_df.loc[floor_id, 'width'] * self.x_scale)
            maxY=int(self.floorPlans_df.loc[floor_id, 'height'] * self.y_scale)
            metersPerUnit = self.floorPlans_df.loc[floor_id, 'metersPerUnit']
            x = (rawX - minX) * metersPerUnit
            y = (rawY - minY) * metersPerUnit
        return x,y
        
    def __processEkahauData(self):

        self.EkahauData = {'building':[],'floors':[],'aps':[]}

        if self.buildingExists:
            # Building data
            address_keys = ['address','city','state','postal_code']
            for building_id, row in self.building_df.iterrows():
                address_list = [x.strip() for x in self.project_info['location'].split(",")]
                res = dict(zip(address_keys, address_list))
                for element in address_keys:
                    if element not in res:
                        res[element] = "Unknown"
                data = {
                    'building_id': building_id,
                    'name': row['name'],
                    'address': res,
                    'xiq_building_id' : None
                }
                if data['address']['address'] == '':
                    data['address']['address'] = 'Unknown'
                self.EkahauData['building'].append(data)

        # Floor data
        for floor_id, row in self.floorPlans_df.iterrows():
            # collect needed data
            if self.buildingExists and floor_id in self.buildingFloors_df['floorPlanId'].unique():
                filt = self.buildingFloors_df['floorPlanId'] == floor_id
                floorHeight = self.buildingFloors_df.loc[filt, 'height'].values[0]
                floorThickness = self.buildingFloors_df.loc[filt, 'thickness'].values[0]
                floorTypeId = self.buildingFloors_df.loc[filt, 'floorTypeId'].values[0]
                buildingId = self.buildingFloors_df.loc[filt, 'buildingId'].values[0]
                if 'propagationProperties' in self.floorTypes_df:
                    propProperties = self.floorTypes_df.loc[floorTypeId,'propagationProperties']
                    floorAttenuation = propProperties[0]['attenuationFactor'] * floorThickness
                elif 'attenuationPerMeter' in self.floorTypes_df:
                    floorAttenuation = self.floorTypes_df.loc[floorTypeId, 'attenuationPerMeter'] * floorThickness
            else:
                floorHeight = 4
                buildingId = None
                floorAttenuation = 15
            row.dropna(inplace=True)
            # Change image names
            if 'bitmapImageId' in row:
                imageType = 'bitmap'
                imageId = row['bitmapImageId']
            else:
                imageType = 'regular'
                imageId = row['imageId']
            floorImageName, width, height = self.__floorImageProcessing(imageId, imageType)

            #Floor Payload
            data = {
                "floor_id" : floor_id, 
                "associated_building_id" : buildingId,
                 "name": row['name'],
                 "environment": "AUTO_ESTIMATE",
                 "db_attenuation": str(floorAttenuation),
                 "measurement_unit": "METERS",
                "installation_height": str(floorHeight),
                "map_size_width": str(width),
                "map_size_height": str(height),
                "map_name": floorImageName,
                "xiq_floor_id" : None
            }
            self.EkahauData['floors'].append(data)
            
        for ap_id, row in self.ap_df.iterrows():
            # collect needed data
            if self.serialInTags:
                ap_name = row['name']
                ap_sn = ''
                for tag in row['tags']:
                    if tag['tagKeyId'] == self.serialTagId:
                        ap_sn = tag['value']
                        break
            else:
                if "::" in row['name']:
                    ap_name, ap_sn = [x.strip() for x in row['name'].split("::")]
                else:
                    ap_name = row['name']
                    ap_sn = ''
            ap_floor_id = (row['location']['floorPlanId'])
            rawX = row['location']['coord']['x']
            rawY = row['location']['coord']['y']
            x,y = self.__updateAPCoord(ap_floor_id,rawX,rawY)
            
            data = {
                'xiq_id': None,
                'name' : ap_name,
                'sn' : ap_sn,
                'location_id' : ap_floor_id,
                'x' : x,
                'y' : y
            }
            self.EkahauData['aps'].append(data)