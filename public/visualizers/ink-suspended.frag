// Original generative artwork. Copyright 2026 Sound/Vision contributors.
// SPDX-License-Identifier: Apache-2.0
// Shared without modification by the WebGL2 player and native film renderer.
uniform vec2 u_resolution;
uniform float u_time;
uniform vec4 u_audio; // low, body, air, low-frequency transient
uniform float u_tick;
uniform float u_energy;
uniform float u_breath;
uniform float u_age;
uniform float u_bands[24];
uniform float u_strength;
uniform float u_motion;
out vec4 fragColor;
const float PI=3.14159265359;
mat2 rotation(float t){float c=cos(t),s=sin(t);return mat2(c,-s,s,c);}
float hash(vec3 p){p=fract(p*.3183099+vec3(.1,.2,.3));p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}
float noise(vec3 p){
  vec3 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+1.),f.x),f.y),f.z);
}
float band(float a){float idx=fract(a/(2.*PI)+.5)*23.;int k=int(floor(idx));return mix(u_bands[k],u_bands[min(k+1,23)],fract(idx));}
vec4 material(vec3 p,float phase){
  float low=u_audio.x*u_strength,body=u_audio.y,air=u_audio.z,hit=u_audio.w*u_strength;
  float r=length(p.xy),a=atan(p.y,p.x);
  float b=band(a);
  float center=.89+.13*sin(3.*a+phase*.72)+.075*sin(5.*a-phase*.3);
  float spread=.235+.17*low+.095*b;
  float edge=(r-center)/spread;
  float radial=exp(-edge*edge*edge*edge*1.25);
  float alive=sqrt(max(hit,0.))*exp(-u_age*1.3)*sin(24.*r-u_age*21.);
  float fold=.25*sin(3.*a+phase)+.11*sin(7.*a-phase*.6);
  fold+=(.13+.09*low)*sin(r*15.-a*2.+phase*.9);
  fold+=.065*sin(a*14.+r*19.-phase)*( .35+air);
  fold+=.12*alive+.12*hit*sin(a*2.-r*8.);
  float fine=noise(p*7.+vec3(0.,0.,phase*.2));
  float distance=p.z-fold-(fine-.5)*.115;
  float thickness=.016+.012*body;
  float density=exp(-abs(distance)/thickness)*radial;
  density*=.84+.16*sin(r*230.+a*13.+fine*7.);
  float da=.75*cos(3.*a+phase)+.77*cos(7.*a-phase*.6)-(.26+.18*low)*cos(r*15.-a*2.+phase*.9);
  float dr=(1.95+1.35*low)*cos(r*15.-a*2.+phase*.9)+.065*19.*cos(a*14.+r*19.-phase)*(.35+air);
  vec3 normal=normalize(vec3(-dr*cos(a)+da*sin(a)/max(r,.1),-dr*sin(a)-da*cos(a)/max(r,.1),1.));
  float key=pow(abs(dot(normal,normalize(vec3(-.6,.8,1.)))),3.);
  float rim=pow(abs(dot(normal,normalize(vec3(1.,-.3,.45)))),6.);
  float silk=pow(abs(normal.z),3.);
  vec3 ink=vec3(.048,.082,.09);
  vec3 pearl=vec3(.87,.90,.82);
  vec3 color=mix(ink,pearl,key*.79+silk*.17);
  color+=vec3(.47,.24,.14)*rim*(.2+.55*b);
  color+=vec3(.29,.43,.45)*pow(1.-abs(normal.z),3.)*.45;
  color+=vec3(.62,.73,.67)*u_tick*.24*pow(max(0.,sin(a*23.+r*37.)),12.);
  color*=.55+.74*body+.42*hit;
  return vec4(color,density);
}
void main(){
  vec2 uv=(gl_FragCoord.xy-.5*u_resolution)/u_resolution.y;
  uv*=max(1.,1.48/(u_resolution.x/u_resolution.y));
  float t=u_time*u_motion,phase=t*.125;
  // Wide, off-axis framing, with a restrained camera orbit through the song.
  vec3 ro=vec3(0.,0.,3.9),rd=normalize(vec3(uv*2.05,-2.5));
  float turn=.22+.12*sin(t*.023);
  ro.xz=rotation(turn)*ro.xz;rd.xz=rotation(turn)*rd.xz;
  ro.yz=rotation(-.29+.055*sin(t*.037))*ro.yz;
  rd.yz=rotation(-.29+.055*sin(t*.037))*rd.yz;
  vec3 col=vec3(.017,.023,.025);
  col+=vec3(.014,.024,.025)*exp(-dot(uv-vec2(.4,.1),uv-vec2(.4,.1))*.8);
  vec3 acc=vec3(0.);float opacity=0.;
  float scale=1.+u_audio.x*u_strength*.11;
  for(int i=0;i<152;i++){
    float d=2.3+float(i)*.0203;
    vec3 p=(ro+rd*d)/scale;
    p.xy=rotation(-.33+.025*sin(t*.04))*p.xy;
    p.x/=(1.33+.04*u_breath);p.y*=1.12;
    vec4 sampleColor=material(p,phase);
    float alpha=1.-exp(-sampleColor.a*1.1);
    acc+=(1.-opacity)*sampleColor.rgb*alpha;
    opacity+=(1.-opacity)*alpha;
    if(opacity>.985)break;
  }
  col=col*(1.-opacity)+acc;
  // Dim motes, fixed to source time. There is no autonomous animation on pause.
  vec2 cell=uv*vec2(105.,90.);
  vec2 id=floor(cell);vec2 f=fract(cell)-.5;
  float seed=hash(vec3(id,7.));
  float mote=exp(-dot(f,f)*550.)*step(.994,seed);
  col+=vec3(.30,.37,.36)*mote*(.11+.28*u_tick);
  float vignette=1.-.28*smoothstep(.5,1.5,length(uv));
  col*=vignette;
  col=pow(max(col,vec3(0.)),vec3(.87));
  float grain=(hash(vec3(gl_FragCoord.xy, floor(t*30.)))-.5)/230.;
  fragColor=vec4(clamp(col+grain,0.,1.),1.);
}
