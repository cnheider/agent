#!/usr/bin/env python3
# coding=utf-8


__author__ = 'cnheider'
"""
Description: Config for training
Author: Christian Heider Nielsen
"""

import utilities as U
# General
from configs.base_config import *
from utilities.random_process.ornstein_uhlenbeck import OrnsteinUhlenbeckProcess

CONFIG_NAME = __name__
CONFIG_FILE = __file__

# Optimiser
OPTIMISER_TYPE = torch.optim.Adam
OPTIMISER_LEARNING_RATE = 0.00025
OPTIMISER_WEIGHT_DECAY = 1e-5
OPTIMISER_ALPHA = 0.95
DISCOUNT_FACTOR = 0.99
TARGET_UPDATE_TAU = 0.001

ACTOR_LEARNING_RATE = 0.0001
CRITIC_LEARNING_RATE = 0.001
Q_WEIGHT_DECAY = 0.01

ACTOR_OPTIMISER_SPEC = U.OSpec(
    constructor=OPTIMISER_TYPE,
    kwargs=dict(lr=ACTOR_LEARNING_RATE),
    )

CRITIC_OPTIMISER_SPEC = U.OSpec(
    constructor=OPTIMISER_TYPE,
    kwargs=dict(lr=CRITIC_LEARNING_RATE, weight_decay=Q_WEIGHT_DECAY),
    )

RANDOM_PROCESS_THETA = 0.15
RANDOM_PROCESS_SIGMA = 0.2
RANDOM_PROCESS = OrnsteinUhlenbeckProcess(theta=RANDOM_PROCESS_THETA, sigma=RANDOM_PROCESS_SIGMA)

MEMORY = U.ReplayMemory(REPLAY_MEMORY_SIZE)

ACTION_CLIPPING = False
SIGNAL_CLIPPING = False

ENVIRONMENT_NAME = 'Pendulum-v0'

# Architecture
ACTOR_ARCH_PARAMS = {
  'input_size':        None,  # Obtain from environment
  'hidden_size':       [128, 64],
  'output_activation': None,
  'output_size':       None  # Obtain from environment
  }
ACTOR_ARCH = U.ActorArchitecture

CRITIC_ARCH_PARAMS = {
  'input_size':        None,  # Obtain from environment
  'hidden_size':       [128, 64],
  'output_activation': None,
  'output_size':       None  # Obtain from environment
  }
CRITIC_ARCH = U.CriticArchitecture
