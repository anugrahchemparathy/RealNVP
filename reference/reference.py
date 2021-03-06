import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions.multivariate_normal import MultivariateNormal


class RealNVPNode(nn.Module):
    def __init__(self, mask, hidden_size):
        super(RealNVPNode, self).__init__()
        self.dim = len(mask)
        self.mask = nn.Parameter(mask, requires_grad=False)

        self.s_func = nn.Sequential(nn.Linear(in_features=self.dim, out_features=hidden_size), nn.LeakyReLU(),
                                    nn.Linear(in_features=hidden_size, out_features=hidden_size), nn.LeakyReLU(),
                                    nn.Linear(in_features=hidden_size, out_features=self.dim))

        self.scale = nn.Parameter(torch.Tensor(self.dim))

        self.t_func = nn.Sequential(nn.Linear(in_features=self.dim, out_features=hidden_size), nn.LeakyReLU(),
                                    nn.Linear(in_features=hidden_size, out_features=hidden_size), nn.LeakyReLU(),
                                    nn.Linear(in_features=hidden_size, out_features=self.dim))

    def forward(self, x):
        x_mask = x*self.mask
        s = self.s_func(x_mask) * self.scale
        t = self.t_func(x_mask)

        y = x_mask + (1 - self.mask) * (x*torch.exp(s) + t)

        # Sum for -1, since for every batch, and 1-mask, since the log_det_jac is 1 for y1:d = x1:d.
        log_det_jac = ((1 - self.mask) * s).sum(-1)
        return y, log_det_jac

    def inverse(self, y):
        y_mask = y * self.mask
        s = self.s_func(y_mask) * self.scale
        t = self.t_func(y_mask)

        x = y_mask + (1-self.mask)*(y - t)*torch.exp(-s)

        inv_log_det_jac = ((1 - self.mask) * -s).sum(-1)

        return x, inv_log_det_jac


class RealNVP(nn.Module):
    def __init__(self, masks, hidden_size):
        super(RealNVP, self).__init__()

        self.dim = len(masks[0])
        self.hidden_size = hidden_size

        self.masks = nn.ParameterList([nn.Parameter(torch.Tensor(mask), requires_grad=False) for mask in masks])
        self.layers = nn.ModuleList([RealNVPNode(mask, self.hidden_size) for mask in self.masks])

        self.distribution = MultivariateNormal(torch.zeros(self.dim), torch.eye(self.dim))

    def log_probability(self, x):
        log_prob = torch.zeros(x.shape[0])
        for layer in reversed(self.layers):
            x, inv_log_det_jac = layer.inverse(x)
            log_prob += inv_log_det_jac
        log_prob += self.distribution.log_prob(x)

        return log_prob

    def rsample(self, num_samples):
        x = self.distribution.sample((num_samples,))
        log_prob = self.distribution.log_prob(x)

        for layer in self.layers:
            x, log_det_jac = layer.forward(x)
            log_prob += log_det_jac

        return x, log_prob

    def sample_each_step(self, num_samples):
        samples = []

        x = self.distribution.sample((num_samples,))
        samples.append(x.detach().numpy())

        for layer in self.layers:
            x, _ = layer.forward(x)
            samples.append(x.detach().numpy())

        return samples
