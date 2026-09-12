import copy
from pathlib import Path

import pytest
from fastapi import HTTPException
from .test_film_review import review
from .film_review import Credits, CreditEdit, Export, read
from .film_credits import credit_lines, credit_windows, render_credits


def test_optional_rows_and_shadow_render_inside_safe_area():
    values=Credits(artist='An Artist',songTitle='A Song',recordLabel='A Label').model_dump()
    image,info=render_credits(values)
    x1,y1,x2,y2=image.getbbox()
    assert 120<=x1<=140 and 820<y1<940 and 1020<y2<1045 and x2<1730
    assert info['lines']==['An Artist','A Song','A Label']
    pixels=image.getdata()
    assert any(r==255 and g==255 and b==255 and a>0 for r,g,b,a in pixels)
    assert any(r==0 and g==0 and b==0 and a>0 for r,g,b,a in pixels)
    assert credit_lines(Credits(songTitle='Only a song').model_dump())==['Only a song']
    assert render_credits(Credits(enabled=False,songTitle='Hidden').model_dump())[0].getbbox() is None
    assert render_credits(Credits(songTitle='W'*160).model_dump())[0].getbbox()[2]<1730
    assert credit_windows(5)==[(.5,4.2)]
    assert credit_windows(30)==[(.7,7.5),(21.5,29.2)]


def test_credit_edit_invalidates_export_but_keeps_takes_and_existing_snapshot(review):
    service,key,_,_=review;original=service.load(key)
    service.submit(key,Export(revision=original['revision'],requestId='export-before-credits'))
    before=read(service.folder(key)/'jobs/export-before-credits/input.json')
    new=service.edit_credits(key,CreditEdit(revision=original['revision'],credits=Credits(artist='New artist',songTitle='Song title',recordLabel='Independent')))
    assert new['cutRevision']==original['cutRevision']+1
    assert service.load(key)['scenes']==original['scenes']
    assert before==read(service.folder(key)/'jobs/export-before-credits/input.json')
    assert new['credits']['recordLabel']=='Independent'
    with pytest.raises(HTTPException):service.edit_credits(key,CreditEdit(revision=original['revision'],credits=Credits()))
    service.update_job(key,'export-before-credits','ready','Test fixture ready')
    service.submit(key,Export(revision=new['revision'],requestId='export-after-credits'))
    after=read(service.folder(key)/'jobs/export-after-credits/input.json')
    assert after['plan']['credits']==new['credits']
