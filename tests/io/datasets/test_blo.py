import os
import pickle
import json

import numpy as np
import pytest

from libertem.job.masks import ApplyMasksJob
from libertem.analysis.raw import PickFrameAnalysis
from libertem.executor.inline import InlineJobExecutor
from libertem.io.dataset.blo import BloDataSet
from libertem.io.dataset.base import TilingScheme
from libertem.common import Shape
from libertem.udf.sumsigudf import SumSigUDF

from utils import dataset_correction_verification, get_testdata_path

BLO_TESTDATA_PATH = os.path.join(get_testdata_path(), 'default.blo')
HAVE_BLO_TESTDATA = os.path.exists(BLO_TESTDATA_PATH)

pytestmark = pytest.mark.skipif(not HAVE_BLO_TESTDATA, reason="need .blo testdata")  # NOQA


@pytest.fixture()
def default_blo():
    ds = BloDataSet(
        path=str(BLO_TESTDATA_PATH),
    )
    ds.initialize(InlineJobExecutor())
    return ds


def test_simple_open(default_blo):
    assert tuple(default_blo.shape) == (90, 121, 144, 144)


def test_check_valid(default_blo):
    assert default_blo.check_valid()


def test_detect():
    assert BloDataSet.detect_params(
        path=str(BLO_TESTDATA_PATH),
        executor=InlineJobExecutor()
    )["parameters"]


def test_read(default_blo):
    partitions = default_blo.get_partitions()
    p = next(partitions)
    # FIXME: partition shape can vary by number of cores
    # assert tuple(p.shape) == (11, 121, 144, 144)
    tileshape = Shape(
        (8,) + tuple(default_blo.shape.sig),
        sig_dims=default_blo.shape.sig.dims
    )
    tiling_scheme = TilingScheme.make_for_shape(
        tileshape=tileshape,
        dataset_shape=default_blo.shape,
    )

    tiles = p.get_tiles(tiling_scheme=tiling_scheme)
    t = next(tiles)
    assert tuple(t.tile_slice.shape) == (8, 144, 144)


def test_pickle_meta_is_small(default_blo):
    pickled = pickle.dumps(default_blo._meta)
    pickle.loads(pickled)
    assert len(pickled) < 512


def test_pickle_fileset_is_small(default_blo):
    pickled = pickle.dumps(default_blo._get_fileset())
    pickle.loads(pickled)
    assert len(pickled) < 1024


def test_apply_mask_on_raw_job(default_blo, lt_ctx):
    mask = np.ones((144, 144))

    job = ApplyMasksJob(dataset=default_blo, mask_factories=[lambda: mask])
    out = job.get_result_buffer()

    executor = InlineJobExecutor()

    for tiles in executor.run_job(job):
        for tile in tiles:
            tile.reduce_into_result(out)

    results = lt_ctx.run(job)
    assert results[0].shape == (90 * 121,)


@pytest.mark.parametrize(
    'TYPE', ['JOB', 'UDF']
)
def test_apply_mask_analysis(default_blo, lt_ctx, TYPE):
    mask = np.ones((144, 144))
    analysis = lt_ctx.create_mask_analysis(factories=[lambda: mask], dataset=default_blo)
    analysis.TYPE = TYPE
    results = lt_ctx.run(analysis)
    assert results[0].raw_data.shape == (90, 121)


def test_sum_analysis(default_blo, lt_ctx):
    analysis = lt_ctx.create_sum_analysis(dataset=default_blo)
    results = lt_ctx.run(analysis)
    assert results[0].raw_data.shape == (144, 144)


def test_pick_job(default_blo, lt_ctx):
    analysis = lt_ctx.create_pick_job(dataset=default_blo, origin=(16,))
    results = lt_ctx.run(analysis)
    assert results.shape == (144, 144)


@pytest.mark.parametrize(
    'TYPE', ['JOB', 'UDF']
)
def test_pick_analysis(default_blo, lt_ctx, TYPE):
    analysis = PickFrameAnalysis(dataset=default_blo, parameters={"x": 16, "y": 16})
    analysis.TYPE = TYPE
    results = lt_ctx.run(analysis)
    assert results[0].raw_data.shape == (144, 144)


@pytest.mark.parametrize(
    "with_roi", (True, False)
)
def test_correction(default_blo, lt_ctx, with_roi):
    ds = default_blo

    if with_roi:
        roi = np.zeros(ds.shape.nav, dtype=bool)
        roi[:1] = True
    else:
        roi = None

    dataset_correction_verification(ds=ds, roi=roi, lt_ctx=lt_ctx, exclude=[(55, 92), (61, 31)])
    dataset_correction_verification(ds=ds, roi=roi, lt_ctx=lt_ctx)


def test_cache_key_json_serializable(default_blo):
    json.dumps(default_blo.get_cache_key())


@pytest.mark.dist
def test_blo_dist(dist_ctx):
    ds = BloDataSet(path="/data/default.blo")
    ds = ds.initialize(dist_ctx.executor)
    analysis = dist_ctx.create_sum_analysis(dataset=ds)
    results = dist_ctx.run(analysis)
    assert results[0].raw_data.shape == (144, 144)


def test_positive_sync_offset(lt_ctx):
    udf = SumSigUDF()
    sync_offset = 2

    ds = lt_ctx.load(
        "blo", path=BLO_TESTDATA_PATH, nav_shape=(4, 2),
    )

    result = lt_ctx.run_udf(dataset=ds, udf=udf)
    result = result['intensity'].raw_data[sync_offset:]

    ds_with_offset = lt_ctx.load(
        "blo", path=BLO_TESTDATA_PATH, nav_shape=(4, 2), sync_offset=sync_offset
    )

    result_with_offset = lt_ctx.run_udf(dataset=ds_with_offset, udf=udf)
    result_with_offset = result_with_offset['intensity'].raw_data[
        :ds_with_offset._meta.shape.nav.size - sync_offset
    ]

    assert np.allclose(result, result_with_offset)


def test_negative_sync_offset(lt_ctx):
    udf = SumSigUDF()
    sync_offset = -2

    ds = lt_ctx.load(
        "blo", path=BLO_TESTDATA_PATH, nav_shape=(4, 2),
    )

    result = lt_ctx.run_udf(dataset=ds, udf=udf)
    result = result['intensity'].raw_data[:ds._meta.shape.nav.size - abs(sync_offset)]

    ds_with_offset = lt_ctx.load(
        "blo", path=BLO_TESTDATA_PATH, nav_shape=(4, 2), sync_offset=sync_offset
    )

    result_with_offset = lt_ctx.run_udf(dataset=ds_with_offset, udf=udf)
    result_with_offset = result_with_offset['intensity'].raw_data[abs(sync_offset):]

    assert np.allclose(result, result_with_offset)


def test_offset_smaller_than_image_count(lt_ctx):
    sync_offset = -10900

    with pytest.raises(Exception) as e:
        lt_ctx.load(
            "blo",
            path=BLO_TESTDATA_PATH,
            sync_offset=sync_offset
        )
    assert e.match(
        r"offset should be in \(-10890, 10890\), which is \(-image_count, image_count\)"
    )


def test_offset_greater_than_image_count(lt_ctx):
    sync_offset = 10900

    with pytest.raises(Exception) as e:
        lt_ctx.load(
            "blo",
            path=BLO_TESTDATA_PATH,
            sync_offset=sync_offset
        )
    assert e.match(
        r"offset should be in \(-10890, 10890\), which is \(-image_count, image_count\)"
    )


def test_reshape_nav(lt_ctx):
    udf = SumSigUDF()

    ds_with_1d_nav = lt_ctx.load("blo", path=BLO_TESTDATA_PATH, nav_shape=(8,))
    result_with_1d_nav = lt_ctx.run_udf(dataset=ds_with_1d_nav, udf=udf)
    result_with_1d_nav = result_with_1d_nav['intensity'].raw_data

    ds_with_2d_nav = lt_ctx.load("blo", path=BLO_TESTDATA_PATH, nav_shape=(4, 2))
    result_with_2d_nav = lt_ctx.run_udf(dataset=ds_with_2d_nav, udf=udf)
    result_with_2d_nav = result_with_2d_nav['intensity'].raw_data

    ds_with_3d_nav = lt_ctx.load("blo", path=BLO_TESTDATA_PATH, nav_shape=(2, 2, 2))
    result_with_3d_nav = lt_ctx.run_udf(dataset=ds_with_3d_nav, udf=udf)
    result_with_3d_nav = result_with_3d_nav['intensity'].raw_data

    assert np.allclose(result_with_1d_nav, result_with_2d_nav, result_with_3d_nav)


def test_incorrect_sig_shape(lt_ctx):
    sig_shape = (5, 5)

    with pytest.raises(Exception) as e:
        lt_ctx.load(
            "blo",
            path=BLO_TESTDATA_PATH,
            sig_shape=sig_shape
        )
    assert e.match(
        r"sig_shape must be of size: 20736"
    )
