#!/usr/bin/env python
import numpy as np

import rospy
from geometry_msgs.msg import PoseStamped, Quaternion, Point
from iai_wsg_50_msgs.msg import PositionCmd, Status
from tf.transformations import quaternion_from_matrix, quaternion_about_axis

from giskardpy.tfwrapper import lookup_pose
from refills_perception_interface.knowrob_wrapper import KnowRob
from refills_perception_interface.move_arm import MoveArm
from refills_perception_interface.move_base import MoveBase

# TODO not below 82 during pick up
# TODO table height = 72
from refills_perception_interface.move_gripper import MoveGripper
from refills_perception_interface.robosherlock_wrapper import RoboSherlock


class CRAM(object):
    def __init__(self):
        path_to_yaml = rospy.get_param('/perception_interface/path_to_json')
        rospy.set_param('~path_to_json', path_to_yaml)

        self.default_object_name = 'box'
        self.kr = KnowRob()
        self.base = MoveBase()
        self.gripper = MoveGripper()
        self.robo_sherlock = RoboSherlock(self.kr, name='RoboSherlock_scenario3', check_camera=False)
        self.arm = MoveArm(tip='gripper_tool_frame', root='base_footprint')
        self.arm.giskard.clear_world()

    def facing_place_pose(self, facing_id, object_height):
        facing_pose = PoseStamped()
        facing_pose.header.frame_id = self.kr.get_object_frame_id(facing_id)
        facing_depth = self.kr.get_facing_depth(facing_id)
        facing_height = self.kr.get_facing_height(facing_id)
        facing_pose.pose.position.y = -facing_depth / 2. - 0.1
        facing_pose.pose.position.z = -facing_height / 2. + object_height / 2 + .06
        facing_pose.pose.orientation = Quaternion(*quaternion_from_matrix(np.array([[1, 0, 0, 0],
                                                                                    [0, 0, 1, 0],
                                                                                    [0, -1, 0, 0],
                                                                                    [0, 0, 0, 1]])))
        return facing_pose

    def refill(self):
        # self.arm.drive_pose()
        empty_facings = self.kr.get_all_empty_facings()
        for facing_id in empty_facings:
            facing_frame_id = self.kr.get_object_frame_id(facing_id)
            if lookup_pose('map', facing_frame_id).pose.position.z > 0.4:
                object_class = self.kr.get_object_of_facing(facing_id)
                width, depth, height = self.kr.get_object_dimensions(object_class)
                # self.spawn_fake_object(width, depth, height)

                self.pickup_object(depth, width, height)
                self.place_object(facing_id, height)

    def goto_see_pose(self):
        base_pose = PoseStamped()
        base_pose.header.frame_id = 'map'
        base_pose.pose.position = Point(2.8, 1., 0)
        base_pose.pose.orientation = Quaternion(*quaternion_about_axis(np.pi, [0, 0, 1]))
        # self.base.move_other_frame(base_pose, 'gripper_tool_frame')
        self.arm.see_pose()


    def pickup_object(self, depth, width, height):
        self.gripper.open()
        self.goto_see_pose()
        pose = self.robo_sherlock.see(depth, width, height)
        self.spawn_fake_object(width, depth, height, pose)
        pass


        # self.arm.place_pose_right()
        # arm_goal = PoseStamped()
        # arm_goal.header.frame_id = 'gripper_tool_frame'
        # arm_goal.pose.position.z = .15
        # arm_goal.pose.orientation.w = 1
        # self.arm.set_and_send_cartesian_goal(arm_goal)
        # base_pose = PoseStamped()
        # base_pose.header.frame_id = 'map'
        # base_pose.pose.position = Point(2, 1.9, 0)
        # base_pose.pose.orientation = Quaternion(*quaternion_about_axis(np.pi, [0, 0, 1]))
        # self.base.move_other_frame(base_pose, 'gripper_tool_frame')
        #
        # arm_goal.header.frame_id = 'map'
        # arm_goal.pose.position = Point(2, 2, .82)
        # arm_goal.pose.orientation = Quaternion(*quaternion_from_matrix(np.array([[1, 0, 0, 0],
        #                                                                          [0, 0, 1, 0],
        #                                                                          [0, -1, 0, 0],
        #                                                                          [0, 0, 0, 1]])))
        # self.arm.giskard.allow_collision(body_b=self.default_object_name)
        # self.arm.set_and_send_cartesian_goal(arm_goal)
        #
        # self.gripper.set_pose(object_width)
        # self.arm.giskard.attach_object(self.default_object_name, 'gripper_tool_frame')
        # arm_goal.header.frame_id = 'gripper_tool_frame'
        # arm_goal.pose.position = Point(0, .1, -.1)
        # self.arm.drive_pose()

    def spawn_fake_object(self, depth, width, height, pose):
        self.arm.giskard.add_box(size=[depth, width, height], pose=pose)

    def place_object(self, facing_id, object_height):
        facing_frame_id = self.kr.get_object_frame_id(facing_id)
        shelf_layer_id = self.kr.get_shelf_layer_from_facing(facing_id)
        shelf_system_id = self.kr.get_shelf_system_from_layer(shelf_layer_id)
        self.goto_pre_place(shelf_system_id, facing_id, facing_frame_id, object_height)

        arm_goal = PoseStamped()
        arm_goal.header.frame_id = 'gripper_tool_frame'
        arm_goal.pose.position.z = 0.13
        arm_goal.pose.orientation.w = 1
        self.arm.giskard.allow_all_collisions()
        self.arm.set_and_send_cartesian_goal(arm_goal)
        self.arm.giskard.detach_object(self.default_object_name)
        rospy.sleep(.5)
        self.arm.giskard.remove_object(self.default_object_name)
        self.kr.add_objects(facing_id, 1)
        self.gripper.release()

        arm_goal = PoseStamped()
        arm_goal.header.frame_id = 'gripper_tool_frame'
        arm_goal.pose.position.z = -0.13
        arm_goal.pose.orientation.w = 1
        self.arm.giskard.allow_all_collisions()
        self.arm.set_and_send_cartesian_goal(arm_goal)

        self.arm.giskard.allow_all_collisions()
        self.arm.place_pose_right()

    def goto_pre_place(self, shelf_system_id, facing_id, facing_frame_id, object_height):
        self.arm.giskard.allow_all_collisions()
        if not self.kr.is_left(shelf_system_id):
            self.arm.place_pose_left()
        else:
            self.arm.place_pose_right()

        base_pose = PoseStamped()
        base_pose.header.frame_id = facing_frame_id
        base_pose.pose.position.y = -.7
        base_pose.pose.orientation = Quaternion(*quaternion_about_axis(np.pi, [0, 0, 1]))
        self.base.move_other_frame(base_pose, 'gripper_tool_frame')
        goal_pose = self.facing_place_pose(facing_id, object_height)
        self.arm.giskard.allow_all_collisions()
        self.arm.set_and_send_cartesian_goal(goal_pose)


if __name__ == '__main__':
    rospy.init_node('cram')
    plan = CRAM()
    plan.refill()