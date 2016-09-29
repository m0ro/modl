# Author: Arthur Mensch
# License: BSD
# Adapted from nilearn example

# Load ADDH
import time
from os.path import join
from tempfile import TemporaryDirectory

import matplotlib.pyplot as plt
from data import load_data, data_ing, patch_ing, make_patches
from joblib import Memory
from modl._utils.system import get_cache_dirs
from modl.dict_fact import DictFact
from modl.plotting.fmri import display_maps
from modl.plotting.images import plot_patches
from sacred import Experiment
from sacred.observers import MongoObserver
from sklearn.feature_extraction.image import extract_patches_2d

import numpy as np

decompose_ex = Experiment('decompose',
                          ingredients=[data_ing, patch_ing])
decompose_ex.observers.append(MongoObserver.create(db_name='images'))


@decompose_ex.config
def config():
    batch_size = 50
    learning_rate = 0.9
    offset = 0
    AB_agg = 'full'
    G_agg = 'full'
    Dx_agg = 'full'
    reduction = 1
    alpha = 1
    l1_ratio = 0
    pen_l1_ratio = 0.9
    n_jobs = 1
    n_epochs = 5
    verbose = 20
    n_components = 100
    n_threads = 3


@data_ing.config
def config():
    source = 'lisboa'
    gray = True
    scale = 4


@patch_ing.config
def config():
    patch_size = (64, 64)
    max_patches = 10000
    test_size = 2000
    normalize_per_channel = True


class ImageScorer():
    @decompose_ex.capture
    def __init__(self, test_data, _run):
        self.start_time = time.clock()
        self.test_data = test_data
        self.test_time = 0
        for info_key in ['score', 'time',
                         'iter', 'profiling',
                         'components',
                         'filename']:
            _run.info[info_key] = []

    @decompose_ex.capture
    def __call__(self, dict_fact, _run):
        test_time = time.clock()

        filename = 'record_%s.npy' % dict_fact.n_iter_

        with TemporaryDirectory() as dir:
            filename = join(dir, filename)
            np.save(filename, dict_fact.components_)
            _run.add_artifact(filename)

        score = dict_fact.score(self.test_data)
        self.test_time += time.clock() - test_time
        this_time = time.clock() - self.start_time - self.test_time

        test_time = time.clock()

        _run.info['time'].append(this_time)
        _run.info['score'].append(score)
        _run.info['profiling'].append(dict_fact.profiling_.tolist())
        _run.info['iter'].append(dict_fact.n_iter_)
        _run.info['components'].append(filename)

        self.test_time += time.clock() - test_time


@decompose_ex.automain
def decompose_run(batch_size,
                  learning_rate,
                  offset,
                  verbose,
                  AB_agg, G_agg, Dx_agg,
                  reduction,
                  alpha,
                  l1_ratio,
                  pen_l1_ratio,
                  n_components,
                  n_threads,
                  n_epochs,
                  _seed,
                  _run
                  ):
    image = load_data(memory=Memory(cachedir=get_cache_dirs()[0],
                                       verbose=0))
    train_data, test_data = make_patches(image)
    print('seed: ', _seed)
    if _run.observers:
        cb = ImageScorer(test_data)
    else:
        cb = None

    dict_fact = DictFact(verbose=verbose,
                         n_epochs=n_epochs,
                         random_state=_seed,
                         n_components=n_components,
                         n_threads=n_threads,
                         pen_l1_ratio=pen_l1_ratio,
                         learning_rate=learning_rate,
                         offset=offset,
                         batch_size=batch_size,
                         AB_agg=AB_agg,
                         G_agg=G_agg,
                         Dx_agg=Dx_agg,
                         reduction=reduction,
                         alpha=alpha,
                         l1_ratio=l1_ratio,
                         callback=cb,
                         )
    dict_fact.fit(train_data)

    with TemporaryDirectory() as dir:
        filename = join(dir, 'components.npy')
        np.save(filename, dict_fact.components_)
        _run.add_artifact(filename)

    fig = plot_patches(dict_fact.components_, _run.info['data_shape'])
    with TemporaryDirectory() as dir:
        filename = join(dir, 'components.png')
        plt.savefig(filename)
        plt.show()
        plt.close(fig)
        _run.add_artifact(filename)
