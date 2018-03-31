"""
Trainer for tsf.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import pdb

import cPickle as pkl
import numpy as np
import tensorflow as tf
import json
import os


from utils import *
import texar as tx
from texar.data.vocabulary import SpecialTokens
from texar.hyperparams import HParams
from texar.models.tsf import TSF

class TSFTrainer:
    """TSF trainer."""
    def __init__(self, hparams=None):
        self._hparams = HParams(hparams, self.default_hparams(),
                                allow_new_hparam=True)

    @staticmethod
    def default_hparams():
        return {
            "train_data_hparams": {
                "batch_size": 64,
                "num_epochs": 20,
                "source_dataset": {
                    "files": "../../data/yelp/sentiment.train.sort.0",
                    "vocab_file": "../../data/yelp/vocab",
                    "bos_token": SpecialTokens.BOS,
                    "eos_token": SpecialTokens.EOS,
                },
                "target_dataset": {
                    "files": "../../data/yelp/sentiment.train.sort.1",
                    "vocab_share": True,
                },
            },
            "val_data_hparams": {
                "batch_size": 64,
                "num_epochs": 1,
                "source_dataset": {
                    "files": "../../data/yelp/sentiment.dev.sort.0",
                    "vocab_file": "../../data/yelp/vocab",
                    "bos_token": SpecialTokens.BOS,
                    "eos_token": SpecialTokens.EOS,
                },
                "target_dataset": {
                    "files": "../../data/yelp/sentiment.dev.sort.1",
                    "vocab_share": True,
                },
            },
            "test_data_hparams": {
                "batch_size": 64,
                "num_epochs": 1,
                "source_dataset": {
                    "files": "../../data/yelp/sentiment.test.sort.0",
                    "vocab_file": "../../data/yelp/vocab",
                    "bos_token": SpecialTokens.BOS,
                    "eos_token": SpecialTokens.EOS,
                },
                "target_dataset": {
                    "files": "../../data/yelp/sentiment.test.sort.1",
                    "vocab_share": True,
                },
            },
            "expt_dir": "../../expt",
            "log_dir": "log",
            "name": "tsf",
            "rho": 1.,
            "gamma_init": 1,
            "gamma_decay": 0.5,
            "gamma_min": 0.001,
            "disp_interval": 100,
            "max_epoch": 20,
        }


  # def eval_model(self, model, sess, vocab, data0, data1, output_path):
  #   batches, order0, order1 = get_batches(
  #     data0, data1, vocab["word2id"],
  #     self._hparams.batch_size, sort=self._hparams.sort_data)
  #   losses = Stats()

  #   data0_ori, data1_ori, data0_tsf, data1_tsf = [], [], [], []
  #   for batch in batches:
  #     logits_ori, logits_tsf = model.decode_step(sess, batch)

  #     loss, loss_g, ppl_g, loss_d, loss_d0, loss_d1 = model.eval_step(
  #       sess, batch, self._hparams.rho, self._hparams.gamma_min)
  #     batch_size = len(batch["enc_inputs"])
  #     word_size = np.sum(batch["weights"])
  #     losses.append(loss, loss_g, ppl_g, loss_d, loss_d0, loss_d1,
  #                   w_loss=batch_size, w_g=batch_size,
  #                   w_ppl=word_size, w_d=batch_size,
  #                   w_d0=batch_size, w_d1=batch_size)
  #     ori = logits2word(logits_ori, vocab["id2word"])
  #     tsf = logits2word(logits_tsf, vocab["id2word"])
  #     half = self._hparams.batch_size // 2
  #     data0_ori += ori[:half]
  #     data1_ori += ori[half:]
  #     data0_tsf += tsf[:half]
  #     data1_tsf += tsf[half:]

  #   n0 = len(data0)
  #   n1 = len(data1)
  #   data0_ori = reorder(order0, data0_ori)[:n0]
  #   data1_ori = reorder(order1, data1_ori)[:n1]
  #   data0_tsf = reorder(order0, data0_tsf)[:n0]
  #   data1_tsf = reorder(order1, data1_tsf)[:n1]

  #   write_sent(data0_ori, output_path + ".0.ori")
  #   write_sent(data1_ori, output_path + ".1.ori")
  #   write_sent(data0_tsf, output_path + ".0.tsf")
  #   write_sent(data1_tsf, output_path + ".1.tsf")
  #   return losses

    def preprocess_input(self, data_batch):
        src = data_batch["source_text_ids"]
        src_len = data_batch["source_length"]
        tgt = data_batch["source_text_ids"]
        tgt_len = data_batch["target_length"]
        l = tf.maximum(tf.shape(src)[1], tf.shape(tgt)[1])
        batch_size = tf.shape(src)[0]
        # padding
        src = tf.pad(src, [[0, 0], [0, l - tf.shape(src)[1]]])
        tgt= tf.pad(tgt, [[0, 0], [0, l - tf.shape(tgt)[1]]])
        # concatenate
        inputs = tf.concat([src, tgt], axis=0)
        inputs_len = tf.concat([src_len, tgt_len], axis=0)
        enc_inputs = tf.reverse_sequence(inputs, inputs_len, seq_dim=1)
        # remove EOS
        enc_inputs = enc_inputs[:, 1:]
        enc_inputs = tf.reverse_sequence(enc_inputs, inputs_len - 1, seq_dim=1)
        dec_inputs = enc_inputs
        enc_inputs = dec_inputs[:, 1:]
        enc_inputs = tf.reverse(enc_inputs, [1])
        targets = inputs[:, 1:]
        weights =  tf.sequence_mask(inputs_len - 1, l - 1, tf.float32)
        labels = tf.concat([tf.zeros([batch_size]),
                            tf.ones([batch_size])],
                           axis=0)
        return {
            "enc_inputs": enc_inputs,
            "dec_inputs": dec_inputs,
            "targets": targets,
            "weights": weights,
            "labels": labels,
        }


    def train(self):
        if "config" in self._hparams.keys():
            with open(self._hparams.config) as f:
                self._hparams = HParams(pkl.load(f))

        log_print("Start training with hparams:")
        log_print(json.dumps(self._hparams.todict(), indent=2))
        if not "config" in self._hparams.keys():
            with open(os.path.join(self._hparams.expt_dir, self._hparams.name)
                      + ".config", "w") as f:
                pkl.dump(self._hparams, f)

        train_data = tx.data.PairedTextData(self._hparams.train_data_hparams)
        val_data = tx.data.PairedTextData(self._hparams.val_data_hparams)
        test_data = tx.data.PairedTextData(self._hparams.test_data_hparams)
        iterator = tx.data.TrainTestDataIterator(train=train_data,
                                                 val=val_data, test=test_data)
        data_batch = iterator.get_next()
        input_tensors = self.preprocess_input(data_batch)

        # # set vocab size
        # self._hparams.vocab_size = vocab["size"]

        # set some hparams here
        
        with tf.Session() as sess:
            sess.run(tf.global_variables_initializer())
            sess.run(tf.local_variables_initializer())
            sess.run(tf.tables_initializer())

            iterator.switch_to_train_data(sess)
            fetches = dict(input_tensors.items() + data_batch.items())
            fetches_ = sess.run(fetches, feed_dict={tx.global_mode():
                                                    tf.estimator.ModeKeys.EVAL})
            pdb.set_trace()
            pritn(fetches_)
      # model = TSF(self._hparams)
      # log_print("finished building model")

      # if "model" in self._hparams.keys():
      #   model.saver.restore(sess, self._hparams.model)
      # else:
      #   sess.run(tf.global_variables_initializer())
      #   sess.run(tf.local_variables_initializer())

      # losses = Stats()
      # gamma = self._hparams.gamma_init
      # step = 0
      # best_dev = float("inf")
      # batches, _, _ = get_batches(train[0], train[1], vocab["word2id"],
      #                             model._hparams.batch_size,
      #                             sort=self._hparams.sort_data)

      # log_dir = os.path.join(self._hparams.expt_dir, self._hparams.log_dir)
      # train_writer = tf.summary.FileWriter(log_dir, sess.graph)

      # for epoch in range(1, self._hparams["max_epoch"] + 1):
      #   # shuffle across batches
      #   log_print("------------------epoch %d --------------"%(epoch))
      #   log_print("gamma %.3f"%(gamma))
      #   if self._hparams.shuffle_across_epoch:
      #     batches, _, _ = get_batches(train[0], train[1], vocab["word2id"],
      #                           model._hparams.batch_size,
      #                           sort=self._hparams.sort_data)
      #   random.shuffle(batches)
      #   for batch in batches:
      #     for _ in range(self._hparams.d_update_freq):
      #       loss_d0 = model.train_d0_step(sess, batch, self._hparams.rho, gamma)
      #       loss_d1 = model.train_d1_step(sess, batch, self._hparams.rho, gamma)

      #     if loss_d0 < 1.2 and loss_d1 < 1.2:
      #       loss, loss_g, ppl_g, loss_d = model.train_g_step(
      #         sess, batch, self._hparams.rho, gamma)
      #     else:
      #       loss, loss_g, ppl_g, loss_d = model.train_ae_step(
      #         sess, batch, self._hparams.rho, gamma)

      #     losses.append(loss, loss_g, ppl_g, loss_d, loss_d0, loss_d1)

      #     step += 1
      #     if step % self._hparams.disp_interval == 0:
      #       log_print("step %d: "%(step) + str(losses))
      #       losses.reset()

      #   # eval on dev
      #   dev_loss = self.eval_model(model, sess, vocab, val[0], val[1],
      #     os.path.join(log_dir, "sentiment.dev.epoch%d"%(epoch)))
      #   log_print("dev " + str(dev_loss))
      #   if dev_loss.loss < best_dev:
      #     best_dev = dev_loss.loss
      #     file_name = (
      #       self._hparams["name"] + "_" + "%.2f" %(best_dev) + ".model")
      #     model.saver.save(
      #       sess, os.path.join(self._hparams["expt_dir"], file_name),
      #       latest_filename=self._hparams["name"] + "_checkpoint",
      #       global_step=step)
      #     log_print("saved model %s"%(file_name))

      #   gamma = max(self._hparams.gamma_min, gamma * self._hparams.gamma_decay)

    # return best_dev

def main(unused_args):
    trainer = TSFTrainer()
    trainer.train()

if __name__ == "__main__":
    tf.app.run()