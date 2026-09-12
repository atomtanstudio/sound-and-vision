// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
// Original procedural artwork. No community shader source is incorporated.
uniform vec2 u_resolution;
uniform float u_time;
uniform vec4 u_audio; // bass, midrange, treble, onset, each in [0, 1]
uniform float u_energy;
uniform float u_strength;
uniform int u_preset;
uniform int u_nextPreset;
uniform float u_blend;
out vec4 fragColor;

const float PI = 3.14159265359;
float hash(vec2 p) { return fract(sin(dot(p,vec2(127.17,311.71)))*43758.213); }
mat2 rot(float a) { float s=sin(a),c=cos(a); return mat2(c,-s,s,c); }
float noise(vec2 p) {
  vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);
}
float field(vec2 p) {
  float v=0.,a=.5;
  for(int i=0;i<4;i++){v+=a*noise(p);p=rot(.47)*p*2.07+3.4;a*=.48;}
  return v;
}
vec4 sound(){return clamp(u_audio*u_strength,0.,1.65);}
float line(float distance,float width){return exp(-abs(distance)/max(width,.0001));}

vec3 tunnel(vec2 p){
  vec4 a=sound(); float t=u_time*.12, r=length(p),an=atan(p.y,p.x);
  float perspective=1./(r+.19), flow=perspective*1.9-t*2.4;
  float sides=cos(an*6.+perspective*.7+t*.55);
  float sculpture=flow+.12*sides+.09*sin(an*3.-t*2.);
  float stripe=abs(fract(sculpture)-.5);
  float ribs=line(stripe,.017+.012*a.x);
  float back=line(stripe,.095);
  float spokes=pow(.5+.5*cos(an*12.+perspective*.8),17.);
  vec3 c=vec3(.017,.022,.041);
  c+=mix(vec3(.18,.12,.30),vec3(.9,.43,.15),.5+.5*sin(perspective*.7-t))*back*.52;
  c+=vec3(1.0,.73,.43)*ribs*(.52+.85*a.w);
  c+=vec3(.22,.32,.60)*spokes*back*.26;
  c*=smoothstep(.02,.24,r);c*=.78+.22*smoothstep(.35,1.1,r);
  return c;
}

float molten(vec2 p,float t){
  p+=vec2(sin(p.y*2.1+t),cos(p.x*2.7-t))*.2;
  return field(p*2.+vec2(t*.31,-t*.13))*.8+sin(p.x*2.3+p.y*1.8+t)*.15;
}
vec3 liquid(vec2 p){
  vec4 a=sound();float t=u_time*.11; p*=1.+a.x*.15;
  float z=molten(p,t),e=.006;
  vec3 n=normalize(vec3((z-molten(p+vec2(e,0),t))/e,(z-molten(p+vec2(0,e),t))/e,.7));
  vec3 reflected=reflect(vec3(0,0,-1),n);
  float studio=pow(max(0.,dot(reflected,normalize(vec3(-.2,.8,1.)))),13.);
  float rim=pow(max(0.,dot(reflected,normalize(vec3(.8,-.1,1.)))),22.);
  float folds=.5+.5*sin(reflected.y*6.+reflected.x*3.);
  vec3 c=mix(vec3(.012,.035,.075),vec3(.33,.43,.56),folds*.7);
  c+=vec3(.98,.79,.51)*studio*(.8+a.w*.9);
  c+=vec3(.34,.62,1.)*rim*(.45+a.z*.6);
  c+=vec3(.18,.12,.09)*smoothstep(.53,.8,z);
  return c;
}

vec3 orbital(vec2 p){
  vec4 a=sound();vec3 c=vec3(.012,.019,.037);float t=u_time*.12;
  p=rot(-.28)*p;
  for(int i=0;i<36;i++){
    float fi=float(i), lane=floor(fi/6.),ang=fi*2.39996+t*(.3+lane*.09);
    float radius=.21+lane*.135;
    vec2 center=vec2(cos(ang)*radius*1.65,sin(ang)*radius*.65);
    center*=1.+a.x*.17;float depth=.5+.5*sin(ang);
    float size=.007+.01*depth+.003*a.w;
    float d=length(p-center);
    vec3 color=mix(vec3(.13,.42,.72),vec3(1.,.71,.39),hash(vec2(fi,4.)));
    c+=color*(exp(-d*d/(size*size))*.8+exp(-d/(size*3.2))*.17)*(1.+a.w*.9);
  }
  for(int i=0;i<6;i++){
    float rr=.21+float(i)*.135;
    float d=abs(length(p/vec2(1.65,.65))/(1.+a.x*.17)-rr);
    c+=vec3(.08,.16,.23)*line(d,.0018)*(.45+a.y*.45);
  }
  c+=vec3(.12,.24,.4)*exp(-length(p)*7.)*(.4+a.x*.5);
  return c;
}

vec3 topographic(vec2 p){
  vec4 a=sound();float t=u_time*.035;
  vec2 q=rot(-.2)*p;
  float h=field(q*1.55+vec2(t,-t*.4))+.17*sin(q.x*1.8+q.y*2.-t);
  h+=a.x*.027*sin(q.x*2.5+q.y*1.7);
  float level=h*19.,edge=abs(fract(level)-.5);
  float contours=line(edge,.024+.022*a.z),wide=line(edge,.12)*.11;
  float major=line(abs(fract(level/4.)-.5),.019);
  vec3 base=mix(vec3(.042,.022,.047),vec3(.21,.065,.07),smoothstep(.25,.78,h));
  base+=mix(vec3(.72,.36,.24),vec3(.92,.77,.58),h)*contours*(.4+.6*a.w);
  base+=vec3(.55,.22,.17)*wide+vec3(.65,.48,.31)*major*.21;
  return base;
}

vec3 radial(vec2 p){
  vec4 a=sound();float t=u_time*.09;float r=length(p),ang=atan(p.y,p.x);
  float pulse=1.+a.x*.11; r/=pulse;
  vec3 c=vec3(.022,.025,.031);
  for(int i=0;i<8;i++){
    float fi=float(i),rr=.15+fi*.093;
    float direction=mod(fi,2.)*2.-1.;
    float divisions=12.+fi*4.;float sector=fract((ang+PI)/6.28318*divisions+t*direction);
    float ring=line(r-rr,.0018+.0016*a.w);
    float dash=smoothstep(.07,.11,sector)*(1.-smoothstep(.70,.75,sector));
    vec3 hue=mix(vec3(.26,.43,.52),vec3(.92,.66,.31),fi/7.);
    c+=hue*ring*dash*(.55+a.w*1.15);
    float tick=line(sector-.08,.024)*step(rr-.025,r)*step(r,rr+.025);
    c+=hue*tick*.28;
  }
  float spokes=pow(max(0.,cos(ang*8.-t)),80.);
  c+=vec3(.68,.39,.20)*spokes*exp(-abs(r-.48)*8.)*.28*(.4+a.y);
  c+=vec3(.8,.72,.55)*line(r-.06,.003)*(.5+a.x);
  return c;
}

vec3 ribbons(vec2 p){
  vec4 a=sound();float t=u_time*.17;vec3 c=vec3(.024,.015,.04);
  p=rot(.3)*p;
  for(int i=0;i<9;i++){
    float fi=float(i),offset=(fi-4.)*.125;
    float y=sin(p.x*2.1+t+fi*.22)*(.21+a.x*.07)+sin(p.x*4.1-t*.61+fi*.48)*.062+offset;
    float d=p.y-y;float width=.026+.018*(.5+.5*sin(p.x+fi));
    float sheet=exp(-d*d/(width*width));float seam=line(d-width*.65,.003);
    vec3 hue=mix(vec3(.10,.36,.5),vec3(.65,.16,.30),fi/8.);
    c+=hue*sheet*(.25+.2*a.y);
    c+=mix(vec3(.55,.88,.9),vec3(1.,.62,.53),fi/8.)*seam*(.23+.64*a.w);
  }
  return c;
}

float octahedron(vec3 p){return (dot(abs(p),vec3(1.))-1.)*.57735027;}
float crystalField(vec3 p){
  float t=u_time*.10;vec4 a=sound();
  p/=1.+a.x*.095;
  p.xz=rot(t*.65)*p.xz;p.yz=rot(.27+sin(t*.5)*.16)*p.yz;
  vec3 core=p;core.xy=rot(t*.31)*core.xy;
  float center=octahedron(core/vec3(.44,.74,.44))*.38;
  // A sixfold cluster of elongated gems, with a second inner stepped surface.
  float angle=atan(p.y,p.x)+t*.15;
  float sector=2.*PI/6.;angle=mod(angle+sector*.5,sector)-sector*.5;
  float radius=length(p.xy);
  vec3 outer=vec3(cos(angle)*radius-.75,sin(angle)*radius,p.z);
  outer.xz=rot(-.26)*outer.xz;
  float crown=octahedron(outer/vec3(.35,.18,.32))*.17;
  vec3 inner=core;inner.xy=rot(.55)*inner.xy;
  float stepped=octahedron(inner/vec3(.58,.38,.38))*.31;
  return min(min(center,stepped),crown);
}
vec3 crystalEnvironment(vec3 direction){
  float broad=pow(max(0.,dot(direction,normalize(vec3(-.6,.8,.9)))),3.);
  float strip=pow(max(0.,dot(direction,normalize(vec3(.7,-.1,1.)))),12.);
  float soft=pow(max(0.,dot(direction,normalize(vec3(-.1,-.7,.5)))),12.);
  vec3 c=mix(vec3(.035,.06,.095),vec3(.24,.37,.48),direction.y*.5+.5);
  float panel=exp(-pow(abs(direction.x+.24)/.14,4.))*smoothstep(-.5,.8,direction.y);
  return c+vec3(.62,.82,.95)*broad+vec3(1.,.72,.37)*strip+vec3(.27,.18,.44)*soft+vec3(.88,.95,1.)*panel*.7;
}
vec3 crystalNormal(vec3 p){
  float e=.0012;
  return normalize(vec3(crystalField(p+vec3(e,0,0))-crystalField(p-vec3(e,0,0)),crystalField(p+vec3(0,e,0))-crystalField(p-vec3(0,e,0)),crystalField(p+vec3(0,0,e))-crystalField(p-vec3(0,0,e))));
}
vec3 crystalline(vec2 p){
  vec4 a=sound();
  vec3 ro=vec3(0,0,3.),rd=normalize(vec3(p*2.05,-2.1)),pos=ro;float travel=0.,d=1.;
  for(int i=0;i<64;i++){
    pos=ro+rd*travel;d=crystalField(pos);
    if(d<.00065||travel>6.)break;travel+=d*.86;
  }
  vec3 c=vec3(.012,.021,.032);
  c+=vec3(.09,.16,.20)*exp(-dot(p,p)*2.5)*(.28+a.x*.14);
  if(travel<6.&&d<.003){
    vec3 n=crystalNormal(pos);
    vec3 reflected=reflect(rd,n),through=refract(rd,n,.68);
    float fresnel=.10+.72*pow(1.-max(0.,dot(-rd,n)),3.);
    // Trace through the interior to another physical facet. Different exit
    // planes create the refractive subdivisions and layered depth of a gem.
    vec3 exitPoint=pos+through*.012;float thickness=.012;
    for(int j=0;j<28;j++){
      float innerDistance=crystalField(exitPoint);
      if(innerDistance>0.&&j>1)break;
      float advance=max(.004,abs(innerDistance)*.83);
      thickness+=advance;exitPoint+=through*advance;
    }
    vec3 exitNormal=crystalNormal(exitPoint);
    vec3 transmitted=refract(through,-exitNormal,1.47);
    if(dot(transmitted,transmitted)<.01)transmitted=reflect(through,-exitNormal);
    vec3 absorption=exp(-vec3(.70,.26,.13)*thickness);
    vec3 glass=mix(crystalEnvironment(transmitted)*absorption,crystalEnvironment(reflected),fresnel);
    // Internal mirrored rays create fine caustic facets rather than a flat fill.
    vec3 inside=abs(pos+through*(.45+.12*sin(u_time*.15)));
    float striation=pow(.5+.5*cos((inside.x-inside.z)*39.+inside.y*16.),16.);
    float seam=pow(max(0.,dot(reflected,normalize(vec3(-.8,.3,1.)))),75.);
    glass+=vec3(.27,.50,.64)*striation*(.08+.10*a.z);
    glass+=vec3(.95,.79,.50)*seam*(.45+a.w*.6);
    c=glass*(1.15+.30*a.y);
  }
  return c;
}

vec3 analog(vec2 p){
  vec4 a=sound();float t=u_time*.075;
  vec2 q=rot(.18)*p;
  float wave=sin(q.x*19.+sin(q.y*3.+t)*2.+t*3.);
  float other=sin((q.x*.89+q.y*.24)*20.-t*1.4+sin(q.y*2.-t)*2.);
  float moire=wave*other;
  float broad=sin(q.x*2.7-q.y*3.1+t);
  vec3 c=mix(vec3(.045,.021,.017),vec3(.59,.28,.13),smoothstep(-.8,.75,moire));
  c=mix(c,vec3(.81,.66,.36),smoothstep(.72,1.,moire)*(.35+a.w*.45));
  c+=vec3(.12,.14,.11)*broad*.17;
  c*=.93+.07*sin(gl_FragCoord.y*PI);
  c*=.75+a.x*.24;return c;
}

vec3 scene(int id,vec2 p){
  if(id==0)return tunnel(p);
  if(id==1)return liquid(p);
  if(id==2)return orbital(p);
  if(id==3)return topographic(p);
  if(id==4)return radial(p);
  if(id==5)return ribbons(p);
  if(id==6)return crystalline(p);
  return analog(p);
}
void main(){
  vec2 p=(gl_FragCoord.xy-.5*u_resolution)/u_resolution.y;
  vec3 c=scene(u_preset,p);
  if(u_blend>.0001)c=mix(c,scene(u_nextPreset,p),smoothstep(0.,1.,u_blend));
  float vignette=1.-.26*smoothstep(.25,1.25,length(p));
  c*=vignette;
  c+=vec3((hash(gl_FragCoord.xy+floor(u_time*24.))-.5)/255.);
  c=1.-exp(-max(c,vec3(0.))*1.22);
  fragColor=vec4(pow(c,vec3(.84)),1.);
}
