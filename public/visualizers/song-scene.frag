// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
// The same shader draws the interactive preview and the exported film.
uniform vec2 u_resolution;
uniform float u_time, u_duration, u_strength, u_energy, u_tick, u_breath;
uniform vec4 u_audio;
uniform float u_bands[24];
uniform sampler2D u_artwork;
uniform int u_surfaceCount;
uniform mat3 u_homography[3];
uniform vec4 u_surfaceStyle[3];
uniform vec3 u_color[3],u_accent[3];
out vec4 fragColor;
float band(float x){float p=clamp(x,0.,1.)*23.;int i=int(floor(p));return mix(u_bands[i],u_bands[min(23,i+1)],fract(p));}
// Positive cubic B-spline: smooth measured contours without hard FFT-bin corners.
float softBand(float x){
  float p=clamp(x,0.,1.)*23.,t=fract(p),t2=t*t,t3=t2*t;int i=int(floor(p));
  return (pow(1.-t,3.)*u_bands[max(0,i-1)]+(3.*t3-6.*t2+4.)*u_bands[i]
    +(-3.*t3+3.*t2+3.*t+1.)*u_bands[min(23,i+1)]+t3*u_bands[min(23,i+2)])/6.;
}
float glow(float distance,float width){float q=distance/max(width,.0001);return exp(-q*q);}
float line(float distance){return glow(distance,.0045)+.34*glow(distance,.015)+.09*glow(distance,.045);}
vec3 spectrum(vec2 p,vec3 a,vec3 b){
  float x=clamp((p.x-.065)/.87,0.,.9999), cell=fract(x*24.);
  float level=clamp(band((floor(x*24.)+.5)/24.)*u_strength,0.,1.);
  float y=(.77-p.y)/.57;
  float segments=step(.16,fract(y*25.));
  float bar=step(.11,cell)*step(cell,.87)*step(0.,y)*step(y,level)*segments;
  bar*=step(.065,p.x)*step(p.x,.935);
  vec3 col=mix(a,b,x)*bar*.88;
  col+=mix(a,b,x)*line(p.y-(.16+.12*(1.-band(x))))*.27*step(.065,p.x)*step(p.x,.935);
  col+=mix(a,b,x)*glow(p.y-(.77-.57*level),.012)*.25*step(.16,cell)*step(cell,.85)*step(.065,p.x)*step(p.x,.935);
  return col;
}
vec3 ribbon(vec2 p,vec3 a,vec3 b){
  float x=clamp((p.x-.055)/.89,0.,1.), taper=pow(max(0.,sin(x*3.14159265)),.7);
  float gate=smoothstep(.002,.04,u_energy), spec=(softBand(x)-.5);
  vec3 col=vec3(0.);
  for(int n=0;n<5;n++){
    float k=float(n)-2., phase=u_time*(.3+float(n)*.012)+float(n)*.65;
    float y=.47+k*.047+taper*(sin(x*7.8-phase)*(.075+.055*u_breath)+spec*.17)*u_strength*gate;
    float strength=(1.-abs(k)*.20)*.57;
    col+=mix(a,b,float(n)/4.)*line(p.y-y)*strength;
  }
  float filament=step(.93,fract(x*48.))*glow(p.y-.58,.08)*band(x)*.14;
  return (col+mix(a,b,x)*filament)*step(.055,p.x)*step(p.x,.945);
}
vec3 halo(vec2 p,vec3 a,vec3 b){
  vec2 d=(p-.5)*2.;float radius=length(d), angle=atan(d.y,d.x)/6.2831853+.5;
  float x=fract(angle*48.), value=band(angle);
  float blade=step(.2,x)*step(x,.8)*step(.54,radius)*step(radius,.57+.26*value*u_strength);
  vec3 col=mix(a,b,angle)*blade*.72;
  col+=mix(a,b,.45)*line((radius-.51-u_audio.x*.022)*.4)*.65;
  col+=a*glow(radius-.46,.055)*u_audio.w*.22;
  return col;
}
vec3 contours(vec2 p,vec3 a,vec3 b){
  vec2 d=(p-.5)*vec2(1.6,2.);float radius=length(d), angle=atan(d.y,d.x);
  float x=angle/6.2831853+.5, wave=softBand(x)*.09+sin(angle*3.+u_time*.13)*u_energy*.022;
  vec3 col=vec3(0.);
  for(int i=0;i<7;i++){
    float k=float(i), r=.18+k*.085+wave*(.6+k*.12)*u_strength;
    col+=mix(a,b,k/6.)*line((radius-r)*.55)*(.50-k*.035);
  }
  return col;
}
void main(){
  vec2 uv=vec2(gl_FragCoord.x/u_resolution.x,1.-gl_FragCoord.y/u_resolution.y);
  vec3 base=texture(u_artwork,uv).rgb;
  for(int i=0;i<3;i++){
    if(i>=u_surfaceCount) break;
    vec3 h=u_homography[i]*vec3(uv,1.);vec2 p=h.xy/h.z;
    if(p.x<0.||p.y<0.||p.x>1.||p.y>1.)continue;
    float edge=min(min(p.x,1.-p.x),min(p.y,1.-p.y));
    float mask=smoothstep(.005,.027,edge), gate=smoothstep(.002,.028,u_energy);
    int effect=int(u_surfaceStyle[i].x+.5);vec3 a=u_color[i],b=u_accent[i],light=vec3(0.);
    if(effect==0)light=spectrum(p,a,b);
    else if(effect==1)light=ribbon(p,a,b);
    else if(effect==2)light=halo(p,a,b);
    else light=contours(p,a,b);
    if(effect<2){
      float progress=clamp(u_time/max(1.,u_duration),0.,1.);
      light+=mix(a,b,.4)*glow(p.y-.88,.0018)*step(.07,p.x)*step(p.x,.07+.86*progress)*.22;
    }
    light=clamp(light*mask*gate*sqrt(u_surfaceStyle[i].y),0.,.96);
    base=1.-(1.-base)*(1.-light);
  }
  fragColor=vec4(base,1.);
}
