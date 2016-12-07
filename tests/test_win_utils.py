# -*- coding: utf-8 -*-

"""
test_win_utils
------------

Tests for `cookiecutter.win_utils` module.
"""

import os
import pytest
import subprocess
import sys
import tempfile

import shutil

WIN_BEFORE_PY32 = sys.platform.startswith('win') and sys.version_info < (3, 2)

if WIN_BEFORE_PY32:
    from cookiecutter import win_utils


def link_target_with_mklink(junction=False):
    """ Helper function to make link not using our win_utils
    """
    target = tempfile.mkdtemp(suffix='_tmp_target')
    source = str(target) + '_link'

    subprocess.check_output([
        'cmd',
        '/c',
        'mklink',
        '/d' if not junction else '/j',
        source,
        target
    ])

    return (source, target)


@pytest.fixture(scope='function')
def link_target_symlink():
    link, target = link_target_with_mklink()
    yield (link, target)
    os.rmdir(link)
    os.rmdir(target)


@pytest.fixture(scope='function')
def link_target_junction():
    link, target = link_target_with_mklink(junction=True)
    yield (link, target)
    os.rmdir(link)
    os.rmdir(target)


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_islink(link_target_symlink):
    source, target = link_target_symlink
    assert win_utils.islink(source)


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_islink_invalid_attributes():
    with pytest.raises(WindowsError):
        win_utils.islink("c:\\doesnotexistspath")


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_readlink(link_target_symlink):
    source, target = link_target_symlink
    assert win_utils.readlink(source) == target


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_readlink_junction(link_target_junction):
    source, target = link_target_junction
    assert win_utils.readlink(source) == target


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_readlink_invalid(mocker, link_target_symlink):
    # invalid path
    with pytest.raises(WindowsError):
        win_utils.readlink("c:\\iamnotarealpath")

    # valid path, not a symlink
    source, target = link_target_symlink
    with pytest.raises(WindowsError):
        win_utils.readlink(target)

    # non-symlink reparse tag
    class MockReparse():
        ReparseTag = 0

    mocker.patch(
        'cookiecutter.win_utils.REPARSE_DATA_BUFFER.from_buffer',
        return_value=MockReparse()
    )

    with pytest.raises(ValueError):
        win_utils.readlink(source)


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_symlink(link_target_symlink):
    source, target = link_target_symlink
    new_link = source + "_new_link"

    win_utils.symlink(target, new_link)

    assert win_utils.islink(new_link)
    assert win_utils.readlink(new_link) == target

    os.rmdir(new_link)


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_symlink_error(link_target_symlink):
    source, target = link_target_symlink

    # error on file exists
    with pytest.raises(WindowsError):
        win_utils.symlink(target, source)


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_copytree(link_target_symlink):
    source, target = link_target_symlink

    subdir1 = os.path.join(target, 'sub1')
    subdir2 = os.path.join(target, 'sub2')

    os.makedirs(subdir1)
    os.makedirs(subdir2)

    new_link = str(subdir1) + "_link"
    win_utils.symlink(subdir1, new_link)

    copied_tree_root = tempfile.mkdtemp(suffix='_copy_trees')

    # don't copy symlinks
    no_syms_root = os.path.join(copied_tree_root, 'no_syms')
    win_utils.copytree(target, no_syms_root)

    assert not win_utils.islink(os.path.join(no_syms_root, 'sub1_link'))
    shutil.rmtree(no_syms_root)

    # copy with symlinks
    syms_root = os.path.join(copied_tree_root, 'syms')
    win_utils.copytree(target, syms_root, symlinks=True)

    assert win_utils.islink(os.path.join(syms_root, 'sub1_link'))
    assert win_utils.readlink(os.path.join(syms_root, 'sub1_link')) == \
        os.path.join(target, 'sub1')
    shutil.rmtree(syms_root)

    os.rmdir(subdir1)
    os.rmdir(subdir2)
    os.rmdir(new_link)
    os.rmdir(copied_tree_root)


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_copytree_error_copy2(mocker, link_target_symlink):
    source, target = link_target_symlink

    subdir1 = os.path.join(target, 'sub1')
    subdir2 = os.path.join(target, 'sub2')
    temp_file = os.path.join(subdir1, 'a.txt')

    os.makedirs(subdir1)
    os.makedirs(subdir2)
    with open(temp_file, 'w') as f:
        f.write('test file')

    new_link = str(subdir1) + "_link"
    win_utils.symlink(subdir1, new_link)

    copied_tree_root = tempfile.mkdtemp(suffix='_copy_trees')

    # raise errors on copy
    mocker.patch(
        'cookiecutter.win_utils.copy2',
        side_effect=OSError('asdf')
    )

    # don't copy symlinks
    no_syms_root = os.path.join(copied_tree_root, 'no_syms')
    with pytest.raises(shutil.Error):
        win_utils.copytree(target, no_syms_root)

    shutil.rmtree(no_syms_root)

    os.remove(temp_file)
    os.rmdir(subdir1)
    os.rmdir(subdir2)
    os.rmdir(new_link)
    os.rmdir(copied_tree_root)


@pytest.mark.skipif(not WIN_BEFORE_PY32, reason='Not Windows + Python < 3.2')
def test_copytree_error_copystat(mocker, link_target_symlink):
    source, target = link_target_symlink

    subdir1 = os.path.join(target, 'sub1')
    subdir2 = os.path.join(target, 'sub2')
    temp_file = os.path.join(subdir1, 'a.txt')

    os.makedirs(subdir1)
    os.makedirs(subdir2)
    with open(temp_file, 'w') as f:
        f.write('test file')

    new_link = str(subdir1) + "_link"
    win_utils.symlink(subdir1, new_link)

    copied_tree_root = tempfile.mkdtemp(suffix='_copy_trees')

    # raise errors on copystat
    mocked_copy2 = mocker.patch(
        'cookiecutter.win_utils.copystat',
        side_effect=OSError('asdf')
    )
    mocked_copy2.side_effect.winerror = None

    # don't copy symlinks
    no_syms_root = os.path.join(copied_tree_root, 'no_syms')
    with pytest.raises(shutil.Error):
        win_utils.copytree(target, no_syms_root)

    shutil.rmtree(no_syms_root)

    os.remove(temp_file)
    os.rmdir(subdir1)
    os.rmdir(subdir2)
    os.rmdir(new_link)
    os.rmdir(copied_tree_root)
