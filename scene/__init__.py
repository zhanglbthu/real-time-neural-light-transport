#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

import os
import random
import json
from utils.system_utils import searchForMaxIteration
from scene.dataset_readers import sceneLoadTypeCallbacks
from scene.gaussian_model import GaussianModel
from arguments import ModelParams
from utils.camera_utils import cameraList_from_camInfos, camera_to_JSON
from utils.light_utils import light_to_JSON
from utils.sh_utils import SH2RGB
import sys
from plyfile import PlyData
import numpy as np
from scene.gaussian_model import BasicPointCloud

class Scene:

    gaussians : GaussianModel

    def __init__(self, 
                 args : ModelParams, 
                 gaussians : GaussianModel, 
                 load_iteration=None, 
                 shuffle=True,
                 resolution_scale=1.0,
                 resolution_scales=[1.0], 
                 model_path="None", 
                 source_path="None",
                 data_type="OpenIllumination",
                 num_pts=100000,
                 radius=1.0,
                 white_bg=False,
                 light_type='OLAT',
                 load_pts=None):
        
        """
        :param path: Path to colmap scene main folder.
        """
        
        self.loaded_iter = None
        self.gaussians = gaussians
        self.model_path = model_path

        if load_iteration:
            if load_iteration == -1:
                self.loaded_iter = searchForMaxIteration(os.path.join(self.model_path, "point_cloud"))
            else:
                self.loaded_iter = load_iteration
            print("Loading trained model at iteration {}".format(self.loaded_iter))

        self.train_cameras = {}
        self.test_cameras = {}

        # change source path
        if os.path.exists(os.path.join(source_path, "sparse")):
            print("Found sparse folder, assuming Colmap data set!")
            scene_info = sceneLoadTypeCallbacks["Colmap"](source_path, "images", args.eval)
            
        elif os.path.exists(os.path.join(source_path, "transforms_train.json")):
            print("Found transforms_train.json file, assuming Blender data set!")
            scene_info = sceneLoadTypeCallbacks["Blender"](source_path,
                                                           num_pts,
                                                           args.eval,
                                                           radius)
        
        elif data_type == "OpenIllumination":
            print("Found OpenIllumination data set!")
            scene_info = sceneLoadTypeCallbacks["OpenIllumination"](source_path, 
                                                                    num_pts, 
                                                                    resolution_scale, 
                                                                    args.eval, 
                                                                    radius,
                                                                    white_bg,
                                                                    light_type)
        
        else:
            assert False, "Could not recognize scene type!"

        if scene_info.light_info is not None:
            print("Loading Light Info")
            self.light_info = scene_info.light_info
        
        if not self.loaded_iter:
            with open(scene_info.ply_path, 'rb') as src_file, open(os.path.join(model_path, "input.ply") , 'wb') as dest_file:
                dest_file.write(src_file.read())
            json_cams = []
            camlist = []
            if scene_info.train_cameras:
                camlist.extend(scene_info.train_cameras)
            if scene_info.test_cameras:
                camlist.extend(scene_info.test_cameras)
                
            print(len(camlist))
                
            for id, cam in enumerate(camlist):
                json_cams.append(camera_to_JSON(id, cam))
            with open(os.path.join(self.model_path, "cameras.json"), 'w') as file:
                json.dump(json_cams, file)

        if shuffle:
            random.shuffle(scene_info.train_cameras)  # Multi-res consistent random shuffling
            random.shuffle(scene_info.test_cameras)  # Multi-res consistent random shuffling

        self.cameras_extent = scene_info.nerf_normalization["radius"]
        print("successfully loaded scene")
        
        for resolution_scale in resolution_scales:
            print("Loading Training Cameras")
            self.train_cameras[resolution_scale] = cameraList_from_camInfos(scene_info.train_cameras, resolution_scale, args)
            print("Loading Test Cameras")
            self.test_cameras[resolution_scale] = cameraList_from_camInfos(scene_info.test_cameras, resolution_scale, args)

        if load_pts:
            # 根据点云文件加载点云
            plydata = PlyData.read(load_pts)
            vertices = plydata['vertex']
            positions = np.vstack([vertices['x'], vertices['y'], vertices['z']]).T
            pts_num = positions.shape[0]
            shs = np.random.random((pts_num, 3)) / 255.0
            pts = BasicPointCloud(points=positions, colors=SH2RGB(shs), normals=np.zeros((pts_num, 3)))
            
            self.gaussians.create_from_pcd(pts, self.cameras_extent)
        else:
            if self.loaded_iter:
                self.gaussians.load_ply(os.path.join(self.model_path,
                                                            "point_cloud",
                                                            "iteration_" + str(self.loaded_iter),
                                                            "point_cloud.ply"))
            else:
                self.gaussians.create_from_pcd(scene_info.point_cloud, self.cameras_extent)

    def save(self, iteration):
        point_cloud_path = os.path.join(self.model_path, "point_cloud/iteration_{}".format(iteration))
        self.gaussians.save_ply(os.path.join(point_cloud_path, "point_cloud.ply"))

    def getTrainCameras(self, scale=1.0):
        return self.train_cameras[scale]

    def getTestCameras(self, scale=1.0):
        return self.test_cameras[scale]
    
    def getLightInfo(self):
        return self.light_info if hasattr(self, 'light_info') else None