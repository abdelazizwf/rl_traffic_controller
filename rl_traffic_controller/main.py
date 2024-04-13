import torch
import logging
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

from rl_traffic_controller import consts
from rl_traffic_controller.agent import Agent
from rl_traffic_controller.networks import DQN, stacks
from rl_traffic_controller.environment import Environment


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

logger = logging.getLogger(__name__)


def init_agent(stack_name: str, load_nets: bool = False) -> Agent:
    """Initializes the agent with a new or a previously saved network.
    
    Args:
        stack_name: ID of the layer stack.
        load_nets: Loads a saved network if `True`.
    
    Returns:
        A new `Agent` instance.
    """
    stack = stacks[stack_name]
    
    policy_net = DQN(stack, stack_name).to(device)
    target_net = DQN(stack, stack_name).to(device)
    
    if load_nets is True:
        try:
            policy_net.load_state_dict(torch.load(f"models/{stack_name}_policy_net.pt"))
            target_net.load_state_dict(torch.load(f"models/{stack_name}_target_net.pt"))
            logger.info("Loaded models successfully")
        except Exception:
            logger.exception("Failed to load models.")
            exit()
    else:
        target_net.load_state_dict(policy_net.state_dict())
    
    return Agent(policy_net, target_net)


def train(
    stack_name: str,
    load_nets: bool = False,
    num_episodes: int = 50,
    image_paths: list[str] = []
) -> None:
    """Trains the agent.
    
    Args:
        stack_name: ID of the layer stack.
        load_nets: Loads a saved network if `True`.
        num_episodes: The number of episodes used in training.
        checkpoints: A flag to enable saving the network after each episode.
        image_paths: A list of image paths representing observations to be used
            to evaluate the agent.
    """
    agent = init_agent(stack_name, load_nets)
    
    env = Environment()
    
    logger.info('Started training.')
    
    agent.train(env, num_episodes)
    
    logger.info('Finished training.')
    
    if len(image_paths) > 0:
        evaluate(stack_name, image_paths, agent)


def display_results(
    image: Image.Image,
    result: Image.Image,
    action_value: float,
) -> None:
    """Displays the input image and the chosen action.
    
    Args:
        image: The input image.
        result: The image of the chosen action.
        action_value: The Q value of the chosen action.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))
        
    ax1.imshow(np.array(image))
    ax1.axis("off")
    
    ax2.imshow(np.array(result))
    ax2.axis("off")
    ax2.set_title(f"Q Value: {str(action_value)}")
    
    fig.tight_layout()
    
    plt.show()


def evaluate(
    stack_name: str,
    image_paths: list[str],
    agent: Agent | None = None
) -> None:
    """Prints the action chosen by the agent given the input observations.
    
    Args:
        stack_name: ID of the layer stack.
        image_paths: A list of image paths representing observations.
        agent: An optional agent that is already initialized.
    """
    if agent is None:
        agent = init_agent(stack_name, True)
    
    for path in image_paths:
        try:
            image = Image.open(path)
        except Exception:
            logger.exception(f"Failed to open image {path}.")
            continue
        
        resized_image = image.resize(consts.IMAGE_SIZE).convert("RGB")
        
        state = torch.tensor(
            np.array(resized_image),
            dtype=torch.float32,
            device=device
        ).permute(2, 0, 1)
        
        values, action = agent.evaluate(state)
        
        print(
            f"\nAction values for {path} are {values}.\n",
            f"The chosen action's index is {action}.\n"
        )
        
        result = Image.open(f"data/phase{action}.jpg")
        
        display_results(image, result, values[action])
