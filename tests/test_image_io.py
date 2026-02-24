from PIL import Image

from app.core.image_io import pad_pair_to_min_side


def test_pad_pair_to_min_side_pads_small_dimension():
    ref = Image.new("RGB", (127, 2), color=(10, 20, 30))
    tst = Image.new("RGB", (127, 2), color=(40, 50, 60))

    out_ref, out_tst = pad_pair_to_min_side(ref, tst, min_side=64)

    assert out_ref.size == (127, 64)
    assert out_tst.size == (127, 64)


def test_pad_pair_to_min_side_keeps_size_when_already_large():
    ref = Image.new("RGB", (256, 128), color=(10, 20, 30))
    tst = Image.new("RGB", (256, 128), color=(40, 50, 60))

    out_ref, out_tst = pad_pair_to_min_side(ref, tst, min_side=64)

    assert out_ref.size == (256, 128)
    assert out_tst.size == (256, 128)
