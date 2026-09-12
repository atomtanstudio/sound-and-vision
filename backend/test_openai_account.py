"""Exercise the real account event loop with an in-memory transport only."""
import asyncio

import pytest

from .openai_account import Account


@pytest.mark.parametrize('images,override,expected',[(False,None,180),(False,600,600),(True,None,600)])
def test_response_deadline_reports_detail_and_interrupts_without_retry(tmp_path,monkeypatch,images,override,expected):
    async def run():
        account=Account(tmp_path);account.models=[{'id':'fixture','default':True}];account.image_skill='/fixture/imagegen'
        calls=[];deadlines=[]
        async def status():return {'connected':True,'images':True}
        async def request(method,params=None,timeout=30):
            calls.append(method)
            if method=='thread/start':return {'thread':{'id':'fixture-thread'}}
            if method=='turn/start':return {'turn':{'id':'fixture-turn'}}
            return {}
        account.status=status;account.request=request
        real_timeout=asyncio.timeout
        def short_timeout(seconds):
            deadlines.append(seconds)
            return real_timeout(.001)
        monkeypatch.setattr(asyncio,'timeout',short_timeout)
        with pytest.raises(RuntimeError,match=f'did not finish within {expected} seconds') as error:
            await account.turn('Synthetic request',images=images,timeout_seconds=override)
        assert isinstance(error.value.__cause__,TimeoutError)
        assert deadlines==[expected] and calls.count('turn/start')==1
        assert 'turn/interrupt' in calls and 'thread/unsubscribe' in calls
        assert not account.listeners
    asyncio.run(run())


def test_transport_timeout_names_the_request_and_cleans_pending_state(tmp_path):
    async def run():
        account=Account(tmp_path);sent=[]
        async def send(message):sent.append(message)
        account.send=send
        with pytest.raises(RuntimeError,match='waiting for turn/start after 0.001 seconds'):
            await account.request('turn/start',{'threadId':'fixture'},timeout=.001)
        assert len(sent)==1 and not account.pending
    asyncio.run(run())


def test_one_account_shares_eight_image_slots_without_blocking_text(tmp_path,monkeypatch):
    monkeypatch.setenv('SOUND_VISION_IMAGE_CONCURRENCY','8')
    async def run():
        account=Account(tmp_path);release=asyncio.Event();full=asyncio.Event();active=0;peak=0;started=[]
        async def response(prompt,schema,model,images,refs,timeout):
            nonlocal active,peak
            if not images:return 'text result'
            started.append(prompt);active+=1;peak=max(peak,active)
            if active==8:full.set()
            try:await release.wait();return prompt
            finally:active-=1
        account._turn=response
        tasks=[asyncio.create_task(account.turn(str(i),images=True)) for i in range(12)]
        await full.wait()
        assert len(started)==8
        assert await account.turn('Text stays available')=='text result'
        release.set()
        assert await asyncio.gather(*tasks)==[str(i) for i in range(12)]
        assert peak==8 and active==0
    asyncio.run(run())
