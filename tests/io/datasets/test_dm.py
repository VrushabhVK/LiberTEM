import os
from glob import glob
import hashlib

import numpy as np
import pytest

from libertem.io.dataset.dm import DMDataSet
from libertem.udf.sum import SumUDF
from libertem.common import Shape
from libertem.udf.sumsigudf import SumSigUDF
from utils import dataset_correction_verification, get_testdata_path
from libertem.io.dataset.base import TilingScheme

DM_TESTDATA_PATH = os.path.join(get_testdata_path(), 'dm')
HAVE_DM_TESTDATA = os.path.exists(DM_TESTDATA_PATH)

pytestmark = pytest.mark.skipif(not HAVE_DM_TESTDATA, reason="need .dm4 testdata")  # NOQA


@pytest.fixture
def default_dm(lt_ctx):
    files = list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4'))))
    ds = lt_ctx.load("dm", files=files)
    return ds


@pytest.fixture
def dm_stack_of_3d(lt_ctx):
    files = list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '3D', '*.dm3'))))
    ds = lt_ctx.load("dm", files=files)
    return ds


def test_simple_open(default_dm):
    assert tuple(default_dm.shape) == (10, 3838, 3710)


def test_check_valid(default_dm):
    default_dm.check_valid()


def test_read_roi(default_dm, lt_ctx):
    roi = np.zeros((10,), dtype=bool)
    roi[5] = 1
    sumj = lt_ctx.create_sum_analysis(dataset=default_dm)
    sumres = lt_ctx.run(sumj, roi=roi)
    sha1 = hashlib.sha1()
    sha1.update(sumres.intensity.raw_data)
    assert sha1.hexdigest() == "e94ed671e20ccce33d288fbcadd0f54691a29b9c"


@pytest.mark.parametrize(
    "with_roi", (True, False)
)
def test_correction(default_dm, lt_ctx, with_roi):
    ds = default_dm

    if with_roi:
        roi = np.zeros(ds.shape.nav, dtype=bool)
        roi[:1] = True
    else:
        roi = None

    dataset_correction_verification(ds=ds, roi=roi, lt_ctx=lt_ctx)


def test_detect_1(lt_ctx):
    fpath = os.path.join(DM_TESTDATA_PATH, '2018-7-17 15_29_0000.dm4')
    assert DMDataSet.detect_params(
        path=fpath,
        executor=lt_ctx.executor,
    )["parameters"] == {
        'files': [fpath],
    }


def test_detect_2(lt_ctx):
    assert DMDataSet.detect_params(
        path="nofile.someext",
        executor=lt_ctx.executor,
    ) is False


def test_same_offset(lt_ctx):
    files = glob(os.path.join(DM_TESTDATA_PATH, '*.dm4'))
    ds = lt_ctx.load("dm", files=files, same_offset=True)
    ds.check_valid()


def test_repr(default_dm):
    assert repr(default_dm) == "<DMDataSet for a stack of 10 files>"


@pytest.mark.dist
def test_dm_dist(dist_ctx):
    files = dist_ctx.executor.run_function(lambda: list(sorted(glob(
        os.path.join(DM_TESTDATA_PATH, "*.dm4")
    ))))
    print(files)
    ds = DMDataSet(files=files)
    ds = ds.initialize(dist_ctx.executor)
    analysis = dist_ctx.create_sum_analysis(dataset=ds)
    roi = np.random.choice([True, False], size=len(files))
    results = dist_ctx.run(analysis, roi=roi)
    assert results[0].raw_data.shape == (3838, 3710)


def test_dm_stack_fileset_offsets(dm_stack_of_3d, lt_ctx):
    fs = dm_stack_of_3d._get_fileset()
    f0, f1 = fs

    # check that the offsets in the fileset are correct:
    assert f0.num_frames == 20
    assert f1.num_frames == 20
    assert f0.start_idx == 0
    assert f0.end_idx == 20
    assert f1.start_idx == 20
    assert f1.end_idx == 40

    lt_ctx.run_udf(dataset=dm_stack_of_3d, udf=SumUDF())


def test_positive_sync_offset(lt_ctx):
    udf = SumSigUDF()
    sync_offset = 2

    ds = lt_ctx.load(
        "dm",
        files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
        nav_shape=(4, 2),
    )

    result = lt_ctx.run_udf(dataset=ds, udf=udf)
    result = result['intensity'].raw_data[sync_offset:]

    ds_with_offset = lt_ctx.load(
        "dm",
        files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
        nav_shape=(4, 2),
        sync_offset=sync_offset
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
        "dm",
        files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
        nav_shape=(4, 2),
    )

    result = lt_ctx.run_udf(dataset=ds, udf=udf)
    result = result['intensity'].raw_data[:ds._meta.shape.nav.size - abs(sync_offset)]

    ds_with_offset = lt_ctx.load(
        "dm",
        files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
        nav_shape=(4, 2),
        sync_offset=sync_offset
    )

    result_with_offset = lt_ctx.run_udf(dataset=ds_with_offset, udf=udf)
    result_with_offset = result_with_offset['intensity'].raw_data[abs(sync_offset):]

    assert np.allclose(result, result_with_offset)


def test_missing_frames(lt_ctx):
    """
    there can be some frames missing at the end
    """
    # one full row of additional frames in the data set than the number of files
    nav_shape = (3, 5)
    files = list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4'))))
    ds = DMDataSet(files=files, nav_shape=nav_shape)
    ds.set_num_cores(4)
    ds = ds.initialize(lt_ctx.executor)

    tileshape = Shape(
        (1,) + tuple(ds.shape.sig),
        sig_dims=ds.shape.sig.dims
    )
    tiling_scheme = TilingScheme.make_for_shape(
        tileshape=tileshape,
        dataset_shape=ds.shape,
    )

    for p in ds.get_partitions():
        for t in p.get_tiles(tiling_scheme=tiling_scheme):
            pass

    assert p._start_frame == 12
    assert p._num_frames == 3
    assert p.slice.origin == (12, 0, 0)
    assert p.slice.shape[0] == 3
    assert t.tile_slice.origin == (9, 0, 0)
    assert t.tile_slice.shape[0] == 1


def test_offset_smaller_than_image_count(lt_ctx):
    sync_offset = -12

    with pytest.raises(Exception) as e:
        lt_ctx.load(
            "dm",
            files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
            sync_offset=sync_offset
        )
    assert e.match(
        r"offset should be in \(-10, 10\), which is \(-image_count, image_count\)"
    )


def test_offset_greater_than_image_count(lt_ctx):
    sync_offset = 12

    with pytest.raises(Exception) as e:
        lt_ctx.load(
            "dm",
            files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
            sync_offset=sync_offset
        )
    assert e.match(
        r"offset should be in \(-10, 10\), which is \(-image_count, image_count\)"
    )


def test_reshape_nav(lt_ctx):
    udf = SumSigUDF()
    files = list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4'))))

    ds_with_1d_nav = lt_ctx.load("dm", files=files, nav_shape=(8,))
    result_with_1d_nav = lt_ctx.run_udf(dataset=ds_with_1d_nav, udf=udf)
    result_with_1d_nav = result_with_1d_nav['intensity'].raw_data

    ds_with_2d_nav = lt_ctx.load("dm", files=files, nav_shape=(4, 2))
    result_with_2d_nav = lt_ctx.run_udf(dataset=ds_with_2d_nav, udf=udf)
    result_with_2d_nav = result_with_2d_nav['intensity'].raw_data

    ds_with_3d_nav = lt_ctx.load("dm", files=files, nav_shape=(2, 2, 2))
    result_with_3d_nav = lt_ctx.run_udf(dataset=ds_with_3d_nav, udf=udf)
    result_with_3d_nav = result_with_3d_nav['intensity'].raw_data

    assert np.allclose(result_with_1d_nav, result_with_2d_nav, result_with_3d_nav)


def test_incorrect_sig_shape(lt_ctx):
    sig_shape = (5, 5)

    with pytest.raises(Exception) as e:
        lt_ctx.load(
            "dm",
            files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
            sig_shape=sig_shape
        )
    assert e.match(
        r"sig_shape must be of size: 14238980"
    )


def test_scan_size_deprecation(lt_ctx):
    scan_size = (2, 2)

    with pytest.warns(FutureWarning):
        ds = lt_ctx.load(
            "dm",
            files=list(sorted(glob(os.path.join(DM_TESTDATA_PATH, '*.dm4')))),
            scan_size=scan_size,
        )
    assert tuple(ds.shape) == (2, 2, 3838, 3710)
