#!/usr/local/bin/python
# coding: utf-8
from functools import wraps
from itertools import count
from typing import Any, Tuple

import draugr
import gym
import numpy

__author__ = 'cnheider'

import torch
from torch import nn, optim
from tqdm import tqdm

import utilities as U
from agents.abstract.joint_ac_agent import JointACAgent


class PPOAgent(JointACAgent):
  '''
'''

  # region Private

  def __defaults__(self) -> None:
    self._steps = 10

    self._discount_factor = 0.99
    self._gae_tau = 0.95
    # self._reached_horizon_penalty = -10.

    self._experience_buffer = U.ExpandableCircularBuffer()
    self._critic_loss = nn.MSELoss
    self._actor_critic_lr = 8e-3
    self._entropy_reg_coef = 3e-4
    self._value_reg_coef = 0.5
    self._batch_size = 32
    self._initial_observation_period = 0
    self._target_update_tau = 1.0
    self._update_target_interval = 1000
    self._max_grad_norm = None
    self._solved_threshold = -200
    self._test_interval = 1000
    self._early_stop = False

    self._state_type = torch.float
    self._value_type = torch.float
    self._action_type = torch.long

    # params for epsilon greedy
    self._epsilon_start = 0.99
    self._epsilon_end = 0.05
    self._epsilon_decay = 500

    self._use_cuda = False

    self._surrogate_clipping_value = 0.2

    self._optimiser_type = torch.optim.Adam

    self._actor_critic_arch = U.ActorCriticNetwork
    self._actor_critic_arch_params = {
      'input_size':   None,
      'hidden_layers':[32, 32],
      'output_size':  [32],
      'heads':        [1, 1],
      'distribution': True
      }

    self._hidden_size = [32]

    self._actor_critic = None
    self._actor_critic_target = None
    self._optimiser = None

  # endregion

  # region Protected

  def _build(self, **kwargs) -> None:
    self._actor_critic_arch_params['input_size'] = self._input_size[0]
    self._actor_critic_arch_params['heads'][0] = self._output_size[0]

    actor_critic = self._actor_critic_arch(**self._actor_critic_arch_params)

    actor_critic_target = self._actor_critic_arch(**self._actor_critic_arch_params)
    actor_critic_target = U.copy_state(actor_critic_target, actor_critic)

    actor_critic.to(self._device)
    actor_critic_target.to(self._device)

    optimiser = self._optimiser_type(actor_critic.parameters(), lr=self._actor_critic_lr)

    self._actor_critic, self._actor_critic_target, self._optimiser = (
      actor_critic, actor_critic_target, optimiser)

  def _optimise_wrt(self, cost, **kwargs):
    self._optimiser.zero_grad()

    cost.backward()

    if self._max_grad_norm is not None:
      nn.utils.clip_grad_norm(self._actor_critic.parameters(), self._max_grad_norm)

    self._optimiser.step()

  def _sample_model(self, state, continuous=True, **kwargs):
    '''
      continuous
        randomly sample from normal distribution, whose mean and variance come from policy network.
        [batch, action_size]

      :param state:
      :type state:
      :param continuous:
      :type continuous:
      :param kwargs:
      :type kwargs:
      :return:
      :rtype:
    '''

    # state = U.to_tensor([state], device=self._device, dtype=self._state_type)

    # if continuous:
    with torch.no_grad():
      distribution, value_estimate = self._actor_critic(state)

      # action = dist.sample()
      # log_prob = dist.log_prob(action)
      # entropy += dist.entropy().mean()

      # a = action.to('cpu').numpy()[0]
      action = distribution.sample()

    action_log_prob = distribution.log_prob(action)

    return action, action_log_prob, value_estimate, distribution
    # else:
    # dist, value_estimate = self._actor_critic(model_input)
    # action = torch.multinomial(softmax_probs)
    # m = Categorical(softmax_probs)
    # action = m.sample()
    # a = action.to('cpu').data.numpy()[0]
    # log_prob = m.log_prob(action)
    # return a, value_estimate, log_prob

  def _train(self, *args, **kwargs):

    # num_updates = int(args.num_frames) // args.num_steps // args.num_processes

    # return self.train_episodically(*args, **kwargs)
    return self.train_step_batched(*args, **kwargs)

  # endregion

  # region Public

  def take_n_steps(self,
                   initial_state,
                   environment,
                   n=100,
                   render=False,
                   render_frequency=100):
    state = initial_state

    accumulated_signal = 0

    transitions = []
    terminated = False
    T = tqdm(range(1, n + 1), f'Step #{self._step_i} - {0}/{n}', leave=False)
    for t in T:
      # T.set_description(f'Step #{self._step_i} - {t}/{n}')
      self._step_i += 1
      dist, value_estimates, *_ = self.sample_action(state)

      action = dist.sample()
      action_prob = dist.log_prob(action)

      next_state, signal, terminated, _ = environment.step(action)

      if render and self._rollout_i % render_frequency == 0:
        environment.render()

      successor_state = None
      if not terminated:  # If environment terminated then there is no successor state
        successor_state = next_state

      transitions.append(
          U.ValuedTransition(
              state,
              action,
              action_prob,
              value_estimates,
              signal,
              successor_state,
              not terminated,
              )
          )

      state = next_state

      accumulated_signal += signal

      if terminated:
        state = environment.reset()
        self._rollout_i += 1

    return transitions, accumulated_signal, terminated, state

  def rollout(self,
              initial_state,
              environment,
              render=False, train=True,
              **kwargs):
    self._rollout_i += 1

    state = initial_state
    episode_signal = 0
    terminated = False
    episode_length = 0
    transitions = []

    T = tqdm(count(1), f'Rollout #{self._rollout_i}', leave=False)
    for t in T:
      self._step_i += 1

      dist, value_estimates, *_ = self.sample_action(state)

      action = dist.sample()
      action_prob = dist.log_prob(action)

      next_state, signal, terminated, _ = environment.step(action)

      if render:
        environment.render()

      successor_state = None
      if not terminated:  # If environment terminated then there is no successor state
        successor_state = next_state

      transitions.append(
          U.ValuedTransition(
              state,
              action,
              action_prob,
              value_estimates,
              signal,
              successor_state,
              not terminated,
              )
          )
      state = next_state

      episode_signal += signal

      if terminated:
        episode_length = t
        break

    return transitions, episode_signal, terminated, state, episode_length

  def back_trace(self, transitions):
    n_step_summary = U.ValuedTransition(*zip(*transitions))

    advantages = U.advantage_estimate(n_step_summary.signal,
                                      n_step_summary.non_terminal,
                                      n_step_summary.value_estimate,
                                      self._discount_factor,
                                      tau=self._gae_tau
                                      )

    value_estimates = U.to_tensor(n_step_summary.value_estimate, device=self._device)

    discounted_returns = value_estimates + advantages

    i = 0
    advantage_memories = []
    for step in zip(*n_step_summary):
      step = U.ValuedTransition(*step)
      advantage_memories.append(
          U.AdvantageMemory(
              step.state,
              step.action,
              step.action_prob,
              step.value_estimate,
              advantages[i],
              discounted_returns[i],
              )
          )
      i += 1

    return advantage_memories

  def evaluate(self, batch, discrete=False, **kwargs):
    # region Tensorise

    states = U.to_tensor(batch.state, device=self._device).view(-1, self._input_size[0])

    value_estimates = U.to_tensor(batch.value_estimate, device=self._device)

    advantages = U.to_tensor(batch.advantage, device=self._device)

    discounted_returns = U.to_tensor(batch.discounted_return, device=self._device)

    action_probs = U.to_tensor(batch.action_prob, device=self._device) \
      .view(-1, self._output_size[0])

    # endregion

    advantage = (advantages - advantages.mean()) / (advantages.std() + self._divide_by_zero_safety)

    _, _, action_probs_old, *_ = self._actor_critic_target(states)

    if discrete:
      actions = U.to_tensor(batch.action, device=self._device) \
        .view(-1, self._output_size[0])
      action_probs = action_probs.gather(1, actions)
      action_probs_old = action_probs_old.gather(1, actions)

    ratio = (action_probs - action_probs_old).exp()
    # Generated action probs from (new policy) and (old policy).
    # Values of [0..1] means that actions less likely with the new policy,
    # while values [>1] mean action a more likely now

    surrogate = ratio * advantage

    clamped_ratio = torch.clamp(ratio, min=1. - self._surrogate_clipping_value,
                                max=1. + self._surrogate_clipping_value)
    surrogate_clipped = clamped_ratio * advantage  # (L^CLIP)

    policy_loss = -torch.min(surrogate, surrogate_clipped).mean()

    entropy_loss = U.entropy(action_probs).mean()

    value_error = (value_estimates - discounted_returns).pow(2).mean()

    collective_cost = policy_loss + value_error * self._value_reg_coef + entropy_loss * self._entropy_reg_coef

    return collective_cost, policy_loss, value_error

  def update(self):
    batch = U.AdvantageMemory(*zip(*self._experience_buffer.sample()))
    collective_cost, actor_loss, critic_loss = self.evaluate(batch)
    self._optimise_wrt(collective_cost)

  def ppo_update(self,
                 ppo_epochs,
                 mini_batch_size,
                 states, actions,
                 log_probs,
                 returns,
                 advantages
                 ):
    for _ in range(ppo_epochs):
      for (state,
           action,
           old_log_probs,
           return_now,
           advantage) in self.ppo_mini_batch_iter(mini_batch_size,
                                                  states,
                                                  actions,
                                                  log_probs,
                                                  returns,
                                                  advantages
                                                  ):
        dist, value = self._actor_critic(state)
        entropy = dist.entropy().mean()
        new_log_probs = dist.log_prob(action)

        ratio = (new_log_probs - old_log_probs).exp()
        surrogate = ratio * advantage
        surrogate_clipped = (torch.clamp(ratio,
                                         1.0 - self._surrogate_clipping_value,
                                         1.0 + self._surrogate_clipping_value)
                             * advantage)

        actor_loss = - torch.min(surrogate, surrogate_clipped).mean()
        critic_loss = (return_now - value).pow(2).mean()

        loss = self._value_reg_coef * critic_loss + actor_loss - self._entropy_reg_coef * entropy

        self._optimiser.zero_grad()
        loss.backward()
        self._optimiser.step()

  #
  def sample_action(self, state, **kwargs) -> Tuple[Any, Any, Any, Any]:
    action, action_log_prob, value_estimate, distribution = self._sample_model(state)

    return action, action_log_prob, value_estimate, distribution

  #
  def train_episodically(self,
                         env,
                         num_batches=10000,
                         render=False,
                         render_frequency=100,
                         stat_frequency=10,
                         **kwargs):

    self._rollout_i = 1

    initial_state = env.reset()

    B = tqdm(range(1, num_batches + 1), f'Batch {0}, {num_batches} - Episode {self._rollout_i}', leave=False)
    for batch_i in B:
      if batch_i % stat_frequency == 0:
        B.set_description(f'Batch {batch_i}, {num_batches} - Episode {self._rollout_i}')

      if render and batch_i % render_frequency == 0:
        transitions, accumulated_signal, terminated, *_ = self.rollout(
            initial_state, env, render=render
            )
      else:
        transitions, accumulated_signal, terminated, *_ = self.rollout(
            initial_state, env
            )

      initial_state = env.reset()

      if batch_i >= self._initial_observation_period:
        advantage_memories = self.back_trace(transitions)

        for memory in advantage_memories:
          self._experience_buffer.add(memory)

        self.update()
        self._experience_buffer.clear()

        if self._rollout_i % self._update_target_interval == 0:
          self._actor_critic_target.load_state_dict(self._actor_critic.state_dict())

      if self._end_training:
        break

    return self._actor_critic, []

  # endregion

  def train_step_batched(self,
                         environments,
                         test_env,
                         *,
                         num_steps=40,
                         max_steps=1000000,
                         ppo_epochs=6,
                         render=True
                         ):
    self.stats = draugr.StatisticCollection(stats=('signal','test_signal', 'entropy'))

    state = environments.reset()

    S = tqdm(range(max_steps), leave=False).__iter__()
    while self._step_i < max_steps and not self._end_training:

      self.batch_entropy = 0
      self.batch_signal = 0

      transitions = []

      successor_state = None

      state = U.to_tensor(state, device=self._device)

      I = tqdm(range(num_steps), leave=False).__iter__()
      for _ in I:

        action, action_log_prob, value_estimate, distribution = self.sample_action(state)
        self.batch_entropy += distribution.entropy().mean().item()

        successor_state, signal, terminated, _ = environments.step(action.cpu().numpy())
        self.batch_signal += signal[0]

        successor_state = U.to_tensor(successor_state, device=self._device)
        signal_ = U.to_tensor(signal, device=self._device).unsqueeze(1)
        not_terminated = U.to_tensor(1 - terminated, device=self._device).unsqueeze(1)

        transitions.append(
            U.ValuedTransition(state,
                               action,
                               action_log_prob,
                               value_estimate,
                               signal_,
                               successor_state,
                               not_terminated
                               # not terminated,
                               )
            )

        state = successor_state

        self._step_i += 1
        S.__next__()

        if self._step_i % self._test_interval == 0:
          test_signals = [self.test_agent(test_env, render=render) for _ in range(10)]
          test_signal = numpy.mean(test_signals)
          self.stats.test_signal.append(test_signal)

          draugr.terminal_plot(self.stats.entropy.values,title='batch_entropy',percent_size=(.8,.25))
          draugr.terminal_plot(self.stats.signal.values,title='batch_signal',percent_size=(.8,.25))
          draugr.terminal_plot(self.stats.test_signal.values,title='test_signal',percent_size=(.8,.3))

          if test_signal > self._solved_threshold and self._early_stop:
            self._end_training = True

      self.stats.signal.append(self.batch_signal)
      self.stats.entropy.append(self.batch_entropy)



      # only calculate value of next state for the last step this time
      _, value_estimate = self._actor_critic(successor_state)

      trans = U.ValuedTransition(*zip(*transitions))
      returns_ = U.compute_gae(value_estimate,
                               trans.signal,
                               trans.non_terminal,
                               trans.value_estimate)

      returns = torch.cat(returns_).detach()
      log_probs = torch.cat(trans.action_prob).detach()
      values = torch.cat(trans.value_estimate).detach()
      states = torch.cat(trans.state)
      actions = torch.cat(trans.action)

      advantage = returns - values

      self.ppo_update(ppo_epochs,
                      self._batch_size,
                      states,
                      actions,
                      log_probs,
                      returns,
                      advantage
                      )

      if self._rollout_i % self._update_target_interval == 0:
        self._actor_critic_target.load_state_dict(self._actor_critic.state_dict())

    return self._actor_critic, []

    '''
        B = tqdm(range(1, num_updates + 1), f'Batch {0}, {num_batches} - Episode {self._rollout_i}', 
        leave=False)
        for batch_i in B:
          if batch_i % stat_frequency == 0:
            B.set_description(f'Batch {batch_i}, {num_batches} - Episode {self._rollout_i}')

          if render and batch_i % render_frequency == 0:
            transitions, accumulated_signal, terminated, initial_state = self.take_n_steps(
                initial_state, env, render=render, n=batch_length
                )
          else:
            transitions, accumulated_signal, terminated, initial_state = self.take_n_steps(
                initial_state, env, n=batch_length
                )

          if batch_i >= self._initial_observation_period:
            advantage_memories = self.back_trace(transitions)
            for m in advantage_memories:
              self._experience_buffer.add(m)

            self.update()
            self._experience_buffer.clear()

            if self._rollout_i % self._update_target_interval == 0:
              self._actor_critic_target.load_state_dict(
                  self._actor_critic.state_dict()
                  )

          if self._end_training:
            break

        return self._actor_critic, []

        '''

  def test_agent(self, test_environment, render=False):
    state = test_environment.reset()
    if render:
      test_environment.render()
    terminal = False
    total_signal = 0
    while not terminal:
      state = U.to_tensor(state, device=self._device).unsqueeze(0)
      dist, _ = self._actor_critic(state)
      next_state, signal, terminal, _ = test_environment.step(dist.sample().cpu().numpy()[0])
      state = next_state
      if render:
        test_environment.render()
      total_signal += signal
    return total_signal

  @staticmethod
  def ppo_mini_batch_iter(mini_batch_size: int,
                          states: Any,
                          actions: Any,
                          log_probs: Any,
                          returns: Any,
                          advantage: Any) -> iter:

    batch_size = states.size(0)
    for _ in range(batch_size // mini_batch_size):
      rand_ids = numpy.random.randint(0, batch_size, mini_batch_size)
      yield (states[rand_ids, :],
             actions[rand_ids, :],
             log_probs[rand_ids, :],
             returns[rand_ids, :],
             advantage[rand_ids, :])


def main():
  # test_agent_main(PPOAgent, C)
  _agent = PPOAgent()

  num_environments = 8
  env_name = 'Pendulum-v0'
  #  env_name = 'MountainCarContinuous-v0'

  def make_env(env_nam):
    @wraps(env_nam)
    def wrapper():
      env = gym.make(env_nam)
      return env

    return wrapper

  _environments = [make_env(env_name) for i in range(num_environments)]
  _environments = U.SubprocVecEnv(_environments)

  _test_env = gym.make(env_name)

  '''
  self._actor_critic = U.ActorCriticNetwork(
      input_size=self._input_size,
      hidden_size=[128],
      output_size=self._output_size,
      heads_hidden_size=[64, 64],
      head_size=[self._output_size[0], 1]
      ).to(self._device)
  '''

  _agent._input_size = _environments.observation_space.shape
  _agent._output_size = _environments.action_space.shape

  _agent._actor_critic = U.ActorCritic(
      _agent._input_size[0],
      _agent._output_size[0],
      _agent._hidden_size[0],
      activation=torch.nn.Tanh()
      ).to(_agent._device)
  _agent._actor_critic_target = U.ActorCritic(
      _agent._input_size[0],
      _agent._output_size[0],
      _agent._hidden_size[0],
      activation=torch.nn.Tanh()
      ).to(_agent._device)

  _agent._actor_critic_target = U.copy_state(_agent._actor_critic_target, _agent._actor_critic)

  _agent._optimiser = optim.Adam(_agent._actor_critic.parameters(), lr=_agent._actor_critic_lr)

  _agent.train(_environments, _test_env)


if __name__ == '__main__':
  main()
