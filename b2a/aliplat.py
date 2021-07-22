#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File    :  aliplat.py
@Date    :  2021/06/17
@Author  :  Yaronzz
@Version :  1.0
@Contact :  yaronhuang@foxmail.com
@Desc    :
"""
import json
import math
import os
from xml.dom.minidom import parseString

import aigpy
import requests
from aigpy.progressHelper import ProgressTool

from b2a.platformImp import *

requests.packages.urllib3.disable_warnings()


class AliUploadLink(object):
    def __init__(self, jsonData, localFilePath, remoteFilePath):
        self.list = jsonData.get('part_info_list', [])
        self.fileId = jsonData.get('file_id')
        self.uploadId = jsonData.get('upload_id')
        self.needUpload = True
        self.localFilePath = localFilePath
        self.remoteFilePath = remoteFilePath

        if 'rapid_upload' in jsonData and jsonData['rapid_upload']:
            self.needUpload = False
        if 'exist' in jsonData and jsonData['exist']:
            self.needUpload = False


class AliKey(object):
    def __init__(self):
        super().__init__()
        self.chunkSize = 10485760
        self.driveId = ''
        self.refreshToken = ''
        self.headers = None
        self.pathIds = {'/': 'root'}

    def login(self, refreshToken: str) -> bool:
        try:
            data = {"refresh_token": refreshToken}
            post_json = requests.post('https://websv.aliyundrive.com/token/refresh',
                                      data=json.dumps(data),
                                      headers={'content-type': 'application/json;charset=UTF-8'},
                                      verify=False).json()
            self.headers = {
                'authorization': post_json['access_token'],
                'content-type': 'application/json;charset=UTF-8'
            }
            self.driveId = post_json['default_drive_id']
            self.refreshToken = post_json['refresh_token']
            return True
        except Exception as e:
            return False

    def __getPathId__(self, remotePath: str):
        if len(remotePath) <= 0:
            remotePath = '/'
        if remotePath in self.pathIds:
            return self.pathIds[remotePath]

        parent = ''
        paths = remotePath.split('/')
        for item in paths:
            key = parent + '/' + item
            key = key.replace('//', '/')
            if key not in self.pathIds:
                res = self.list(parent)
                if len(res) <= 0:
                    return None
                if key not in self.pathIds:
                    return None
            parent = key

        return self.pathIds[remotePath]

    def __updatePathId__(self, path: str, sid: str):
        self.pathIds[path] = sid

    def list(self, remotePath: str) -> List[FileAttr]:
        remotePath = remotePath.rstrip('/')
        sid = self.__getPathId__(remotePath)
        if not sid:
            return []

        try:
            requests_data = {"drive_id": self.driveId, "parent_file_id": sid}
            requests_post = requests.post('https://api.aliyundrive.com/v2/file/list',
                                          data=json.dumps(requests_data),
                                          headers=self.headers,
                                          verify=False).json()
            ret = []
            for item in requests_post['items']:
                obj = FileAttr()
                obj.isfile = item['type'] != 'folder'
                obj.name = item['name']
                obj.path = remotePath + '/' + item['name']
                obj.uid = item['file_id']
                obj.size = item['size'] if 'size' in item else 0
                if not obj.isfile:
                    self.__updatePathId__(obj.path, obj.uid)

                ret.append(obj)
            return ret

        except:
            return []

    def __mkdir__(self, folderName, parentFolderId='root') -> (bool, str):
        folderName = folderName.strip('/')
        try:
            requests_data = {
                "drive_id": self.driveId,
                "parent_file_id": parentFolderId,
                "name": folderName,
                "check_name_mode": "refuse",
                "type": "folder"
            }
            post_json = requests.post('https://api.aliyundrive.com/v2/file/create',
                                      data=json.dumps(requests_data),
                                      headers=self.headers,
                                      verify=False).json()
            return True, post_json.get('file_id')
        except:
            return False, ''

    def __formatRemotePath__(self, remotePath: str) -> str:
        remotePath = remotePath.rstrip('/')
        remotePath = remotePath.replace('//', '/')
        return remotePath

    def mkdirs(self, remotePath: str) -> bool:
        remotePath = remotePath.rstrip('/')
        if self.__getPathId__(remotePath):
            return True

        parent = ''
        paths = remotePath.split('/')
        for item in paths:
            key = parent + '/' + item
            key = key.replace('//', '/')
            if key not in self.pathIds:
                check, keyId = self.__mkdir__(item, self.pathIds[parent])
                if not check:
                    return False
                self.__updatePathId__(key, keyId)
            parent = key

        return True

    def uploadLink(self, localFilePath: str, remoteFilePath: str) -> AliUploadLink:
        filesize = os.path.getsize(localFilePath)
        filename = os.path.basename(localFilePath)
        hashcode = aigpy.file.getHash(localFilePath)
        if filesize <= 0:
            return None

        remotePath = aigpy.path.getDirName(remoteFilePath)
        remotePath = self.__formatRemotePath__(remotePath)
        if not self.mkdirs(remotePath):
            return None

        try:
            part_info_list = []
            for i in range(0, math.ceil(filesize / self.chunkSize)):
                part_info_list.append({'part_number': i + 1})

            requests_data = {
                "drive_id": self.driveId,
                "part_info_list": part_info_list,
                "parent_file_id": self.__getPathId__(remotePath),
                "name": filename,
                "type": "file",
                "check_name_mode": "refuse",
                "size": filesize,
                "content_hash": hashcode,
                "content_hash_name": 'sha1'
            }

            requests_post_json = requests.post('https://api.aliyundrive.com/v2/file/create',
                                               data=json.dumps(requests_data),
                                               headers=self.headers,
                                               verify=False).json()

            ret = AliUploadLink(requests_post_json, localFilePath, remoteFilePath)
            return ret
        except Exception as e:
            return None

    def __getXmlValue__(self, xml_string, tag_name):
        DOMTree = parseString(xml_string)
        DOMTree = DOMTree.documentElement
        tag = DOMTree.getElementsByTagName(tag_name)
        if len(tag) > 0:
            for node in tag[0].childNodes:
                if node.nodeType == node.TEXT_NODE:
                    return node.data
        return False

    # def __getUploadUrl__(self, fileId, filesize, uploadId):
    #     try:
    #         part_info_list = []
    #         for i in range(0, math.ceil(filesize / self.chunk_size)):
    #             part_info_list.append({'part_number': i + 1})

    #         requests_data = {
    #             "drive_id": self.driveId,
    #             "file_id": fileId,
    #             "part_info_list": part_info_list,
    #             "upload_id": uploadId,
    #         }
    #         requests_post = requests.post('https://api.aliyundrive.com/v2/file/get_upload_url',
    #                                       data=json.dumps(requests_data),
    #                                       headers=self.headers,
    #                                       verify=False
    #                                       )
    #         requests_post_json = requests_post.json()
    #         return requests_post_json.get('part_info_list')
    #     except:
    #         return ''

    def uploadFile(self, link: AliUploadLink, showProgress: bool = True) -> bool:
        if not link:
            return False
        if not link.needUpload:
            return True

        try:
            totalSize = os.path.getsize(link.localFilePath)
            progress = ProgressTool(totalSize, 15) if showProgress else None
            index = 0
            curcount = 0
            with open(link.localFilePath, 'rb') as f:
                while True:
                    chunk = f.read(self.chunkSize)

                    res = requests.put(url=link.list[index]['upload_url'],
                                       data=chunk,
                                       verify=False,
                                       timeout=None)

                    if 400 <= res.status_code < 600:
                        # message = self.__getXmlValue__(res.text, 'Message')
                        # if message == 'Request has expired.':
                        #     part_upload_url_list = self.__getUploadUrl__(file_id, filesize, upload_id)
                        #     if part_upload_url_list == '':
                        #         return False
                        #     continue
                        code = self.__getXmlValue__(res.text, 'Code')
                        if code == 'PartAlreadyExist':
                            pass
                        else:
                            res.raise_for_status()
                            return False
                    index += 1
                    curcount += len(chunk)
                    if progress:
                        progress.setCurCount(curcount)
                    if curcount >= totalSize:
                        break

            complete_data = {"drive_id": self.driveId,
                             "file_id": link.fileId,
                             "upload_id": link.uploadId
                             }
            requests_post_json = requests.post('https://api.aliyundrive.com/v2/file/complete',
                                               json.dumps(complete_data),
                                               headers=self.headers,
                                               verify=False).json()
            if 'file_id' in requests_post_json:
                return True
        except Exception as e:
            return False


class AliPlat(PlatformImp):
    def __init__(self):
        super().__init__()

    def list(self, remotePath: str, includeSubDir: bool = False) -> List[FileAttr]:
        array = []
        res = self.key.list(remotePath)
        for item in res:
            array.append(item)
            if includeSubDir and not item.isfile:
                subarr = self.list(item.path, includeSubDir)
                array.extend(subarr)
        return array

    def downloadFile(self, remoteFilePath: str, localFilePath: str) -> bool:
        return False

    def uploadFile(self, localFilePath: str, remoteFilePath: str) -> bool:
        link = self.key.uploadLink(localFilePath, remoteFilePath)
        if not link:
            return False
        check = self.key.uploadFile(link)
        return check

    def downloadLink(self, remoteFilePath: str):
        return None

    def uploadLink(self, localFilePath: str, remoteFilePath: str):
        link = self.key.uploadLink(localFilePath, remoteFilePath)
        return link

    def isFileExist(self, remoteFilePath: str) -> bool:
        path = aigpy.path.getDirName(remoteFilePath)
        name = aigpy.path.getFileName(remoteFilePath)
        array = self.key.list(path)
        for item in array:
            if item.name == name:
                return True
        return False