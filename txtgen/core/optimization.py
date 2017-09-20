#
"""
Various optimization related utilities.
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division

import inspect

import tensorflow as tf

from txtgen.hyperparams import HParams
from txtgen.core import utils


def default_optimization_hparams():
    """Returns default hyperparameters of optimization.

    Returns:
        dict: A dictionary with the following structure and values:

    .. code-block:: python

        {
        }

    """
    return {
        "optimizer": {
            "type": "AdamOptimizer",
            "kwargs": {
                "learning_rate": 0.001
            }
        },
        "learning_rate_decay": {
            "type": "",
            "kwargs": {},
            "min_learning_rate": 0.,
            "start_decay_step": 0,
            "end_decay_step": utils.MAX_SEQ_LENGTH,
        },
        "gradient_clip": {
            "type": "",
            "kwargs": {}
        }
    }

# TODO(zhiting): add YellowFin optimizer
def get_optimizer(hparams):
    """Creates an optimizer based on hyperparameters.

    See the :attr:"optimizer" field in
    :meth:`~txtgen.core.optimization.default_optimization_hparams` for the
    hyperparameters.

    Args:
        hparams (dict or HParams): hyperparameters.

    Returns:
        An instance of :class:`~tensorflow.train.Optimizer`.
    """
    opt_type = hparams["type"]
    opt_kwargs = hparams["kwargs"]
    if opt_kwargs is HParams:
        opt_kwargs = opt_kwargs.todict()
    opt_modules = ['txtgen.custom',
                   'tensorflow.train',
                   'tensorflow.contrib.opt']
    opt = utils.get_instance(opt_type, opt_kwargs, opt_modules)

    return opt

def get_learning_rate_decay_fn(hparams):
    """Creates learning rate decay function based on the hyperparameters.

    See the :attr:`learning_rate_decay` field in
    :meth:`~txtgen.core.optimization.default_optimization_hparams` for the
    hyperparameters.

    Args:
        hparams (dict or HParams): hyperparameters.

    Returns:
        function or None: If :attr:`hparams["type"]` is specified, returns a
        function that takes :attr:`learning_rate` and :attr:`global_step` and
        returns a scalar Tensor representing the decayed learning rate. If
        :attr:`hparams["type"]` is empty, returns `None`.
    """
    fn_type = hparams["type"]
    if fn_type is None or fn_type == "":
        return None

    fn_modules = ["txtgen.custom", "tensorflow.train"]
    decay_fn = utils.get_function(fn_type, fn_modules)
    fn_kwargs = hparams["kwargs"]
    if fn_kwargs is HParams:
        fn_kwargs = fn_kwargs.todict()

    start_step = tf.to_int32(hparams["start_decay_step"])
    end_step = tf.to_int32(hparams["end_decay_step"])

    def lr_decay_fn(learning_rate, global_step):
        """Learning rate decay function.

        Args:
            learning_rate (float or Tensor): The original learning rate.
            global_step (int or scalar int Tensor): optimization step counter.

        Returns:
            scalar float Tensor: decayed learning rate.
        """
        offset_global_step = tf.minimum(
            tf.to_int32(global_step), end_step) - start_step
        if decay_fn == tf.train.piecewise_constant:
            decayed_lr = decay_fn(x=offset_global_step, **fn_kwargs)
        else:
            fn_kwargs_ = {
                "learning_rate": learning_rate,
                "global_step": offset_global_step}
            fn_kwargs_.update(fn_kwargs)
            decayed_lr = utils.call_function_with_redundant_kwargs(
                decay_fn, fn_kwargs_)

            decayed_lr = tf.maximum(decayed_lr, hparams["min_learning_rate"])

        return decayed_lr

    return lr_decay_fn


def get_gradient_clip_fn(hparams):
    """Creates gradient clipping function based on the hyperparameters.

    See the :attr:`gradient_clip` field in
    :meth:`~txtgen.core.optimization.default_optimization_hparams` for the
    hyperparameters.

    Args:
        hparams (dict or HParams): hyperparameters.

    Returns:
        function or None: If :attr:`hparams["type"]` is specified, returns a
        function that takes a list of `(gradients, variables)` tuples and
        returns a list of `(clipped_gradients, variables)` tuples. If
        :attr:`hparams["type"]` is empty, returns `None`.
    """
    fn_type = hparams["type"]
    if fn_type is None or fn_type == "":
        return None

    fn_modules = ["txtgen.custom", "tensorflow"]
    clip_fn = utils.get_function(fn_type, fn_modules)
    clip_fn_args = inspect.getargspec(clip_fn).args
    fn_kwargs = hparams["kwargs"]
    if fn_kwargs is HParams:
        fn_kwargs = fn_kwargs.todict()

    def grad_clip_fn(grads_and_vars):
        """Gradient clipping function.

        Args:
            grads_and_vars (list): A list of `(gradients, variables)` tuples.

        Returns:
            list: A list of `(clipped_gradients, variables)` tuples.
        """
        grads, vars_ = zip(*grads_and_vars)
        if clip_fn == tf.clip_by_global_norm:
            clipped_grads, _ = clip_fn(t_list=grads, **fn_kwargs)
        elif 't_list' in clip_fn_args:
            clipped_grads = clip_fn(t_list=grads, **fn_kwargs)
        elif 't' in clip_fn_args:     # e.g., tf.clip_by_value
            clipped_grads = [clip_fn(t=grad, **fn_kwargs) for grad in grads]

        return list(zip(clipped_grads, vars_))

    return grad_clip_fn

