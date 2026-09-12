import asyncio
from types import SimpleNamespace

import pytest

from .image_jobs import image_batch,configured_concurrency


@pytest.mark.parametrize('limit',[1,8,12])
def test_parallel_images_obey_the_limit_and_keep_scene_order(limit):
    async def run():
        active=0;peak=0;phases=[]
        async def image(index):
            nonlocal active,peak
            active+=1;peak=max(peak,active)
            await asyncio.sleep(.002*((15-index)%3+1))
            active-=1
            return f'frame-{index}'
        result=await image_batch(SimpleNamespace(image_concurrency=limit),range(16),image,phases.append,'Storyboard frames')
        assert peak==limit and result==[f'frame-{i}' for i in range(16)]
        assert phases[-1]=='Storyboard frames · 16/16 complete · 0 active'
    asyncio.run(run())


def test_failure_retains_inflight_results_and_does_not_start_remaining_images(tmp_path):
    async def run():
        ready=asyncio.Event();started=[];finished=[]
        async def image(index):
            started.append(index)
            if len(started)==3:ready.set()
            await ready.wait()
            if index==0:raise RuntimeError('Provider declined this image.')
            await asyncio.sleep(.002)
            (tmp_path/f'frame-{index}.png').write_bytes(b'synthetic image')
            finished.append(index)
        with pytest.raises(RuntimeError,match='Provider declined this image'):
            await image_batch(SimpleNamespace(image_concurrency=3),range(12),image,lambda _:None,'Frames')
        assert sorted(started)==[0,1,2] and sorted(finished)==[1,2]
        assert len(list(tmp_path.glob('*.png')))==2
    asyncio.run(run())


def test_cancelling_a_batch_cleans_up_its_active_workers():
    async def run():
        entered=asyncio.Event();active=set()
        async def image(index):
            active.add(index)
            if len(active)==3:entered.set()
            try:await asyncio.Event().wait()
            finally:active.remove(index)
        batch=asyncio.create_task(image_batch(SimpleNamespace(image_concurrency=3),range(12),image,lambda _:None,'Frames'))
        await entered.wait();batch.cancel()
        with pytest.raises(asyncio.CancelledError):await batch
        assert not active
    asyncio.run(run())


def test_concurrency_setting_is_an_explicit_app_limit(monkeypatch):
    monkeypatch.delenv('SOUND_VISION_IMAGE_CONCURRENCY',raising=False)
    assert configured_concurrency()==8
    monkeypatch.setenv('SOUND_VISION_IMAGE_CONCURRENCY','12')
    assert configured_concurrency()==12
    for value in ('0','33','unlimited'):
        monkeypatch.setenv('SOUND_VISION_IMAGE_CONCURRENCY',value)
        with pytest.raises(ValueError):configured_concurrency()
