#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import Type, Union

import gym

from neodroid.environments.environment import Environment
from neodroid.environments.gym_environment import NeodroidGymWrapper
from neodroid.environments.unity_environment.vector_unity_environment import (
    VectorUnityEnvironment,
)

from neodroidagent.procedures.training import OnPolicyEpisodic, Procedure
from neodroidagent.sessions.single_agent.environment_session import EnvironmentSession
from trolls.wrappers.vector_environments import VectorWrap
from warg.kw_passing import super_init_pass_on_kws

__author__ = "Christian Heider Nielsen"
__doc__ = ""


@super_init_pass_on_kws
class LinearSession(EnvironmentSession):
    def __init__(
        self,
        *,
        environment_name: Union[str, Environment] = "",
        procedure: Union[Type[Procedure], Procedure] = OnPolicyEpisodic,
        environment_type: Union[bool, str] = False,
        **kwargs
    ):
        if isinstance(environment_type, str):
            assert environment_name != ""
            environment_name = VectorWrap(
                NeodroidGymWrapper(gym.make(environment_name))
            )
        elif isinstance(environment_type, bool):
            environment_name = VectorUnityEnvironment(
                name=environment_name, connect_to_running=environment_type
            )

        super().__init__(environments=environment_name, procedure=procedure, **kwargs)


if __name__ == "__main__":
    import neodroidagent.configs.agent_test_configs.pg_test_config as C
    from neodroidagent.agents.torch_agents.model_free.on_policy import PGAgent

    env = VectorUnityEnvironment(
        name=C.ENVIRONMENT_NAME, connect_to_running=C.EnvironmentType
    )
    env.seed(C.SEED)

    LinearSession(procedure=OnPolicyEpisodic)(PGAgent, config=C, environment=env)
