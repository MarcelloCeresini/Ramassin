import pickle
import os
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.callbacks import ModelCheckpoint

# from tensorflow.keras.utils.generic_utils import get_custom_objects

from .callbacks import EpochCounter, HistoryLogger
from .utils import merge_dicts_with_only_lists_as_values

import sys
sys.path.append("~/github/Ramassin")
import loss_func

class ResumableModel(object):
    """Save and overwrite a model to 'to_path',
    preserving the number of epochs and the history dict over multiple interrupted
    executions.

    If to_path is "model", then there will be model_epoch_num.pkl and
    model_history.pkl in the same directory as mymodel, which hold backups for
    the epoch counter and the history dict, respectively.

    Args:
    to_path (str): A path to a model destination, which is
      where model weights will be saved.

    Returns: A Keras History.history dictionary of the entire training process.
    """
    def __init__(self, model, to_path, custom_objects=None):
        self.model = model
        self.to_path = to_path
        self.dir_name = os.path.dirname(to_path)
        self.custom_objects = custom_objects

        # recover latest epoch
        self.epoch_num_file = self.to_path + "_epoch_num.pkl"
        self.initial_epoch = self.get_epoch_num()
        # recover history
        self.history_file = self.to_path + "_history.pkl"
        self.history = self.get_history()

        # recover model from path
        if os.path.exists(self.to_path):
            # get_custom_objects().update(self.custom_objects)
            self.model = load_model(self.to_path, custom_objects=self.custom_objects)
            print(f"Recovered model from {self.to_path} at epoch {self.initial_epoch}.")
        else:
            os.mkdir(self.to_path)

    def _load_pickle(self, filePath, default_value):
        if os.path.exists(filePath) and os.path.getsize(filePath)>0:
            with open(filePath, 'rb') as f:
                return pickle.load(f)
        else:
            return default_value

    def get_epoch_num(self):
        return self._load_pickle(self.epoch_num_file, 0)

    def get_history(self):
        return self._load_pickle(self.history_file, {})

    def _make_fit_args(self, *args, **kwargs):
        assert not 'initial_epoch' in kwargs
        # add callbacks for periodic checkpointing
        if 'callbacks' not in kwargs:
            kwargs['callbacks'] = []
        kwargs['callbacks'].append(HistoryLogger(history_path=self.history_file, recovered_history=self.history))
        kwargs['callbacks'].append(ModelCheckpoint(self.to_path, verbose=True, save_best_only=True))
        kwargs['callbacks'].append(EpochCounter(counter_path=self.epoch_num_file))
        # Warn user if the training is already complete.
        if 'epochs' in kwargs and self.initial_epoch >= kwargs['epochs']:
            epochs = kwargs['epochs']
            print(f'You want to train for {epochs} epochs but {self.initial_epoch} epochs already completed; nothing to do.')
        return args, kwargs

    def _perform_final_save(self, remaining_history, epoch):
        # Combine histories and save
        combined_history = merge_dicts_with_only_lists_as_values([self.history, remaining_history.history])
        # Dump history
        print("writing history")
        with open(self.history_file, "wb") as f:
            pickle.dump(combined_history, f)
        print("finished writing history")
        # Dump last last epoch
        print("writing epoch")
        with open(self.epoch_num_file, "wb") as f:
            pickle.dump(epoch, f)
        print("finished writing epoch")
        # # Save model
        # print("saving")
        # self.model.save(self.to_path)
        # print("finished")
        return combined_history

    def fit(self, *args, **kwargs):
        args, kwargs = self._make_fit_args(*args, **kwargs)
        remaining_history = self.model.fit(initial_epoch=self.initial_epoch, *args, **kwargs)
        combined_history = self._perform_final_save(remaining_history, epoch=kwargs['epochs'])
        return combined_history

    def fit_generator(self, *args, **kwargs):
        args, kwargs = self._make_fit_args(*args, **kwargs)
        remaining_history = self.model.fit_generator(initial_epoch=self.initial_epoch, *args, **kwargs)
        combined_history = self._perform_final_save(remaining_history, epoch=kwargs['epochs'])
        return combined_history
