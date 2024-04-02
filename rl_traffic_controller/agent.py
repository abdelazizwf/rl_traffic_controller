import random
import math
from collections import namedtuple, deque
from itertools import count

import matplotlib.pyplot as plt

import torch
import torch.nn as nn
import torch.optim as optim


# Choose cuda if a GPU is available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


Transition = namedtuple(
    'Transition',
    ('state', 'action', 'next_state', 'reward')
)
Transition.__doc__ = """\
A data record of the environment transition.
"""


class ReplayMemory:
    """A memory buffer to store and sample transitions.
    
    Attributes:
        memory: A `collection.deque` object to hold transitions.
    """

    def __init__(self, capacity: int):
        """
        Args:
            capacity: Maximum number of stored transitions.
        """
        self.memory = deque([], maxlen=capacity)

    def push(self, *args):
        """Saves a transition.
        
        Args:
            *args: Transition elements.
        """
        self.memory.append(Transition(*args))

    def sample(self, batch_size: int) -> list[Transition]:
        """Samples a random number of transitions.
        
        Args:
            batch_size: Number of randomly sampled transitions.
        
        Returns:
            A list of sampled transitions.
        """
        return random.sample(self.memory, batch_size)

    def __len__(self) -> int:
        return len(self.memory)


class DQN(nn.Module):
    """A CNN to predict Q-values.
    
    Attributes:
        layer_stack: A sequence containing the network's layers.
    """

    def __init__(self, n_actions: int):
        """
        Args:
            n_actions: Number of output Q values associated with actions.
        """
        super(DQN, self).__init__()
        self.layer_stack = nn.Sequential(
            nn.Conv2d(3, 16, 7, 3),
            nn.ReLU(),
            nn.Conv2d(16, 64, 5, 2),
            nn.ReLU(),
            nn.Conv2d(64, 128, 3, 1),
            nn.ReLU(),
            nn.Conv2d(128, 256, 3, 1),
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(256 * 17 * 36, n_actions)
        )

    # Called with either one element to determine next action, or a batch
    # during optimization. Returns tensor([[left0exp,right0exp]...]).
    def forward(self, x: torch.Tensor):
        return self.layer_stack(x)


class Agent:
    """The Reinforcement Learning agent.
    
    Attributes:
        BATCH_SIZE: The number of transitions sampled from the replay buffer.
        GAMMA: The discount factor of future state-action values.
        EPS_START: The starting value of epsilon.
        EPS_END: The final value of epsilon.
        EPS_DECAY: Controls the rate of exponential decay of epsilon,
            higher means a slower decay.
        TAU: The update rate of the target network.
        LR: The learning rate of the optimizer
        n_actions: The number of available actions.
        policy_net: The policy Q-network.
        target_net: The target Q-network.
        optimizer: The optimization function.
        memory: The replay memory.
        steps_done: A time step counter used to calculate the epsilon threshold.
        episode_durations: A list of the durations of each episode.
    """
    # UPDATE dot variables
    BATCH_SIZE = 32
    GAMMA = 0.99
    EPS_START = 0.9
    EPS_END = 0.05
    EPS_DECAY = 1000
    TAU = 0.005
    LR = 1e-4

    n_actions = 4

    policy_net = DQN(n_actions).to(device)
    target_net = DQN(n_actions).to(device)
    target_net.load_state_dict(policy_net.state_dict())

    optimizer = optim.AdamW(policy_net.parameters(), lr=LR, amsgrad=True)
    memory = ReplayMemory(2000)

    steps_done = 0
    
    episode_durations = []
    
    @classmethod
    def select_action(cls, state: torch.Tensor) -> torch.Tensor:
        """Given a state, selects an action using epsilon greedy policy.
        
        Args:
            state: A state from the environment.
        
        Returns:
            An action index wrapped in a 2D tensor.
        """
        global steps_done
        sample = random.random()
        eps_threshold = cls.EPS_END + (cls.EPS_START - cls.EPS_END) * \
            math.exp(-1. * cls.steps_done / cls.EPS_DECAY)
        cls.steps_done += 1
        if sample > eps_threshold:
            with torch.no_grad():
                # t.max(1) will return the largest column value of each row.
                # second column on max result is index of where max element was
                # found, so we pick action with the largest expected reward.
                return cls.policy_net(state).max(1).indices.view(1, 1)
        else:
            return torch.tensor(
                [[random.randint(0, 3)]], device=device, dtype=torch.long
            )
    
    @classmethod
    def plot_durations(cls, show_result: bool = False):
        """Plots the duration of episodes, along with an average over the last 100 episodes.
        
        Args:
            show_result: A flag to indicate the plot is showing the final results.
        """
        plt.figure(1)
        durations_t = torch.tensor(cls.episode_durations, dtype=torch.float)
        if show_result:
            plt.title('Result')
        else:
            plt.clf()
            plt.title('Training...')
        plt.xlabel('Episode')
        plt.ylabel('Duration')
        plt.plot(durations_t.numpy())
        # Take 100 episode averages and plot them too
        if len(durations_t) >= 100:
            means = durations_t.unfold(0, 100, 1).mean(1).view(-1)
            means = torch.cat((torch.zeros(99), means))
            plt.plot(means.numpy())

        plt.pause(0.001)  # pause a bit so that plots are updated
    
    @classmethod
    def optimize_model(cls):
        """Performs the model optimization step using batch gradient descent."""
        if len(cls.memory) < cls.BATCH_SIZE:
            return
        transitions = cls.memory.sample(cls.BATCH_SIZE)
        # Transpose the batch (see https://stackoverflow.com/a/19343/3343043 for
        # detailed explanation). This converts batch-array of Transitions
        # to Transition of batch-arrays.
        batch = Transition(*zip(*transitions))

        # Compute a mask of non-final states and concatenate the batch elements
        # (a final state would've been the one after which simulation ended)
        non_final_mask = torch.tensor(
            tuple(map(lambda s: s is not None, batch.next_state)),
            device=device, dtype=torch.bool
        )
        non_final_next_states = torch.cat(
            [s for s in batch.next_state if s is not None]
        )
        state_batch = torch.cat(batch.state)
        action_batch = torch.cat(batch.action)
        reward_batch = torch.cat(batch.reward)

        # Compute Q(s_t, a) - the model computes Q(s_t), then we select the
        # columns of actions taken. These are the actions which would've been taken
        # for each batch state according to policy_net
        state_action_values = cls.policy_net(state_batch).gather(1, action_batch)

        # Compute V(s_{t+1}) for all next states.
        # Expected values of actions for non_final_next_states are computed based
        # on the "older" target_net; selecting their best reward with max(1).values
        # This is merged based on the mask, such that we'll have either the expected
        # state value or 0 in case the state was final.
        next_state_values = torch.zeros(cls.BATCH_SIZE, device=device)
        with torch.no_grad():
            next_state_values[non_final_mask] = cls.target_net(non_final_next_states).max(1).values
        # Compute the expected Q values
        expected_state_action_values = (next_state_values * cls.GAMMA) + reward_batch

        # Compute Huber loss
        criterion = nn.SmoothL1Loss()
        loss = criterion(state_action_values, expected_state_action_values.unsqueeze(1))

        # Optimize the model
        cls.optimizer.zero_grad()
        loss.backward()
        # In-place gradient clipping
        torch.nn.utils.clip_grad_value_(cls.policy_net.parameters(), 100)
        cls.optimizer.step()
    
    @classmethod
    def main(cls, num_episodes: int = 50, checkpoints: bool = False):
        """Performs the main training loops for the given number of episodes.
        
        Args:
            num_episodes: Number of episodes to use in training.
            checkpoints: A flag to enable saving of the model after each episode.
        """
        for i_episode in range(num_episodes):
            # Initialize the environment and get its state
            state = env.reset()
            state = torch.tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
            for t in count():
                action = cls.select_action(state)
                observation, reward, terminated, truncated, _ = env.step(action.item())
                reward = torch.tensor([reward], device=device)
                done = terminated or truncated

                if terminated:
                    next_state = None
                else:
                    next_state = torch.tensor(
                        observation, dtype=torch.float32, device=device
                    ).unsqueeze(0)

                # Store the transition in memory
                cls.memory.push(state, action, next_state, reward)

                # Move to the next state
                state = next_state

                # Perform one step of the optimization (on the policy network)
                cls.optimize_model()

                # Soft update of the target network's weights
                # θ′ ← τ θ + (1 −τ )θ′
                target_net_state_dict = cls.target_net.state_dict()
                policy_net_state_dict = cls.policy_net.state_dict()
                for key in policy_net_state_dict:
                    target_net_state_dict[key] = (policy_net_state_dict[key] * cls.TAU) + \
                        (target_net_state_dict[key] * (1 - cls.TAU))
                cls.target_net.load_state_dict(target_net_state_dict)

                if done:
                    cls.episode_durations.append(t + 1)
                    cls.plot_durations()
                    break
            
            if checkpoints is True:
                torch.save(cls.target_net.state_dict(), "models/target_net.pt")
                torch.save(cls.policy_net.state_dict(), "models/policy_net.pt")

        print('Complete')
        cls.plot_durations(show_result=True)
        plt.ioff()
        plt.show()
