import test from 'node:test';
import assert from 'node:assert/strict';
import {applyDescription, descriptionMatches} from '../src/music-studio/description.ts';

test('description completion replaces the prompt actually used while keeping unrelated edits', () => {
  const source={description:'industrial metal',style:'Old hidden style'};
  const form={...source,title:'New title typed during request',lyrics:'My lyrics',abc:'My score',count:2};
  const result=applyDescription(form,source,'Industrial metal with a female vocalist and mechanical drums.');
  assert.equal(result.style,'');
  assert.match(result.description,/female vocalist/);
  assert.equal(result.title,form.title);
  assert.equal(result.lyrics,form.lyrics);
  assert.equal(result.abc,form.abc);
  assert.equal(result.count,2);
  assert.equal(form.description,'industrial metal');
});
test('completion cannot overwrite a description or advanced style edited while waiting', () => {
  const source={description:'',style:''};
  for(const form of [{description:'Keep my new idea',style:''},{description:'',style:'New advanced style'}]) {
    assert.equal(descriptionMatches(form,source),false);
    assert.equal(applyDescription(form,source,'An AI idea'),form);
  }
});
