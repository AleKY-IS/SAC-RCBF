import gym
from gym import spaces
import numpy as np


class UnicycleEnv(gym.Env):
    """Custom Environment that follows gym interface"""

    metadata = {'render.modes': ['human']}

    def __init__(self, noisy=False):

        super(UnicycleEnv, self).__init__()

        # Define action and observation space
        # They must be gym.spaces objects
        # Example when using discrete actions:
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(2,))
        self.observation_space = spaces.Box(low=-1e10, high=1e10, shape=(7,))
        self.bds = np.array([[-3., -3.], [3., 3.]])
        self.hazards_radius = 0.6
        self.hazards_locations = np.array([[0., 0.], [-1., 1.], [-1., -1.], [1., -1.], [1., 1.]]) * 1.5
        self.dt = 0.02
        self._max_episode_steps = 1000
        self.reward_goal = 1.0
        self.goal_size = 0.3
        # Initialize Env
        self.state = None
        self.episode_step = 0
        self.goal_pos = np.array([2.5, 2.5])
        self.reset()
        # Get Dynamics
        self.get_f, self.get_g = self._get_dynamics()
        # Disturbance
        self.disturbed_dynamics = noisy
        self.disturb_mean = np.zeros((3,))
        self.disturb_covar = np.diag([0.005, 0.005, 0.05]) * 10


    def step(self, action):
        """Organize the observation to understand what's going on

        Parameters
        ----------
        action : ndarray
                Action that the agent takes in the environment

        Returns
        -------
        new_obs : ndarray
          The new observation with the following structure:
          [pos_x, pos_y, cos(theta), sin(theta), xdir2goal, ydir2goal, dist2goal]

        """

        state, reward, done, info = self._step(action)
        return self.get_obs(), reward, done, info

    def _step(self, action):
        """

        Parameters
        ----------
        action

        Returns
        -------
        state : ndarray
            New internal state of the agent.
        reward : float
            Reward collected during this transition.
        done : bool
            Whether the episode terminated.
        info : dict
            Additional info relevant to the environment.
        """

        # Start with our prior for continuous time system x' = f(x) + g(x)u
        self.state += self.dt * (self.get_f(self.state) + self.get_g(self.state) @ action)
        if self.disturbed_dynamics:
            self.state += self.dt * np.random.multivariate_normal(self.disturb_mean, self.disturb_covar, 1).squeeze()

        self.episode_step += 1

        info = dict()

        dist_goal = self._goal_dist()
        reward = (self.last_goal_dist - dist_goal)
        self.last_goal_dist = dist_goal
        # Check if goal is met
        if self.goal_met():
            info['goal_met'] = True
            reward += self.reward_goal
            done = True
        else:
            done = self.episode_step >= self._max_episode_steps


        # Include constraint cost in reward
        if np.any(np.sum((self.state[:2] - self.hazards_locations)**2, axis=1) < self.hazards_radius**2):
            info['cost'] += 0.1

        return self.state, reward, done, info

    def goal_met(self):
        """Return true if the current goal is met this step

        Returns
        -------
        goal_met : bool
            True if the goal condition is met.

        """

        return np.linalg.norm(self.state[:2] - self.goal_pos) <= self.goal_size

    def reset(self):
        """ Reset the state of the environment to an initial state.

        Returns
        -------
        observation : ndarray
            Next observation.
        """

        self.episode_step = 0

        # Re-initialize state
        self.state = np.array([-2.5, -2.5, 0.])

        # Re-initialize goal
        self.goal_pos = np.array([2.5, 2.5])

        # Re-initialize last goal dist
        self.last_goal_dist = self._goal_dist()

        # TODO: Randomize this
        return self.get_obs()

    def render(self, mode='human', close=False):
        """Render the environment to the screen

        Parameters
        ----------
        mode : str
        close : bool

        Returns
        -------

        """

        rel_loc = self.goal_pos - self.state[:2]
        theta_error = np.arctan2(rel_loc[1], rel_loc[0]) - self.state[2]

        print('Ep_step = {}, \tState = {}, \tDist2Goal = {}, alignment_error = {}'.format(self.episode_step, self.state, self._goal_dist(), theta_error))

    def get_obs(self):
        """Given the state, this function returns it to an observation akin to the one obtained by calling env.step

        Parameters
        ----------

        Returns
        -------
        observation : ndarray
          Observation: [pos_x, pos_y, cos(theta), sin(theta), xdir2goal, ydir2goal, exp(-dist2goal)]
        """

        rel_loc = self.goal_pos - self.state[:2]
        goal_dist = np.linalg.norm(rel_loc)
        goal_compass = self.obs_compass()  # compass to the goal

        return np.array([self.state[0], self.state[1], np.cos(self.state[2]), np.sin(self.state[2]), goal_compass[0], goal_compass[1], np.exp(-goal_dist)])

    def _get_dynamics(self):
        """Get affine CBFs for a given environment.

        Parameters
        ----------

        Returns
        -------
        get_f : callable
                Drift dynamics of the continuous system x' = f(x) + g(x)u
        get_g : callable
                Control dynamics of the continuous system x' = f(x) + g(x)u
        """

        def get_f(state):
            f_x = np.zeros(state.shape)
            return f_x

        def get_g(state):
            theta = state[2]
            g_x = np.array([[np.cos(theta), 0],
                            [np.sin(theta), 0],
                            [            0, 1.0]])
            return g_x

        return get_f, get_g

    def obs_compass(self):
        """
        Return a robot-centric compass observation of a list of positions.
        Compass is a normalized (unit-lenght) egocentric XY vector,
        from the agent to the object.
        This is equivalent to observing the egocentric XY angle to the target,
        projected into the sin/cos space we use for joints.
        (See comment on joint observation for why we do this.)
        """

        # Get ego vector in world frame
        vec = self.goal_pos - self.state[:2]
        # Rotate into frame
        R = np.array([[np.cos(self.state[2]), -np.sin(self.state[2])], [np.sin(self.state[2]), np.cos(self.state[2])]])
        vec = np.matmul(vec, R)
        # Normalize
        vec /= np.sqrt(np.sum(np.square(vec))) + 0.001
        return vec

    def _goal_dist(self):
        return np.linalg.norm(self.goal_pos - self.state[:2])
