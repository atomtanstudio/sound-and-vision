// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
// macOS accelerated offscreen OpenGL; raw RGB frames are streamed to stdout.
#define GL_SILENCE_DEPRECATION
#include <OpenGL/OpenGL.h>
#include <OpenGL/gl3.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

std::string readFile(const char* path) {
  std::ifstream in(path); if(!in) throw std::runtime_error(std::string("Cannot read ")+path);
  return std::string(std::istreambuf_iterator<char>(in), {});
}
GLuint compile(GLenum type,const std::string& source) {
  GLuint shader=glCreateShader(type);const char* ptr=source.c_str();
  glShaderSource(shader,1,&ptr,nullptr);glCompileShader(shader);
  GLint ok=0;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
  if(!ok){char log[8192];glGetShaderInfoLog(shader,sizeof log,nullptr,log);throw std::runtime_error(log);}
  return shader;
}
int main(int argc,char** argv) {
  try {
    if(argc!=5&&argc!=7&&argc!=9)throw std::runtime_error("Usage: visualizer-native shader.frag frames.csv width height [strength shade [scene.txt artwork.rgb]] > frames.rgb");
    float response=argc>=7?std::stof(argv[5]):1.f,shade=argc>=7?std::stof(argv[6]):0.f;
    if(!std::isfinite(response)||response<.25f||response>2.f||!std::isfinite(shade)||shade<0.f||shade>1.f)throw std::runtime_error("Invalid visualizer strength or shade");
    int width=std::stoi(argv[3]),height=std::stoi(argv[4]);
    if(width<16||height<16||width>7680||height>7680)throw std::runtime_error("Unsupported frame dimensions");
    CGLPixelFormatAttribute attrs[]={kCGLPFAOpenGLProfile,(CGLPixelFormatAttribute)kCGLOGLPVersion_3_2_Core,kCGLPFAAccelerated,(CGLPixelFormatAttribute)0};
    CGLPixelFormatObj pixelFormat=nullptr;CGLContextObj context=nullptr;GLint count=0;
    CGLError result=CGLChoosePixelFormat(attrs,&pixelFormat,&count);
    if(result!=kCGLNoError||!pixelFormat)throw std::runtime_error("No accelerated CGL pixel format");
    result=CGLCreateContext(pixelFormat,nullptr,&context);CGLDestroyPixelFormat(pixelFormat);
    if(result!=kCGLNoError||!context)throw std::runtime_error("Could not create accelerated OpenGL context");
    CGLSetCurrentContext(context);
    std::cerr<<"Renderer: "<<glGetString(GL_RENDERER)<<"; "<<glGetString(GL_VERSION)<<"\n";
    GLuint vs=compile(GL_VERTEX_SHADER,"#version 330 core\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.-1.,0.,1.);}");
    std::string fragment=readFile(argv[1]);auto end=fragment.rfind('}');
    if(end==std::string::npos)throw std::runtime_error("Invalid shader main");
    fragment.insert(end,"fragColor.rgb=mix(fragColor.rgb,vec3(8.,7.,10.)/255.,u_shade);\n");
    GLuint fs=compile(GL_FRAGMENT_SHADER,"#version 330 core\nuniform float u_shade;\n"+fragment);
    GLuint program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);glLinkProgram(program);
    GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);
    if(!linked){char log[8192];glGetProgramInfoLog(program,sizeof log,nullptr,log);throw std::runtime_error(log);}
    glDeleteShader(vs);glDeleteShader(fs);glUseProgram(program);
    GLuint vao=0,fbo=0,texture=0;glGenVertexArrays(1,&vao);glBindVertexArray(vao);
    glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGB8,width,height,0,GL_RGB,GL_UNSIGNED_BYTE,nullptr);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
    if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)throw std::runtime_error("Incomplete framebuffer");
    glViewport(0,0,width,height);glPixelStorei(GL_PACK_ALIGNMENT,1);
    auto uniform=[&](const char* name){return glGetUniformLocation(program,name);};
    GLint res=uniform("u_resolution"),tim=uniform("u_time"),snd=uniform("u_audio"),eng=uniform("u_energy"),strength=uniform("u_strength"),pre=uniform("u_preset"),nxt=uniform("u_nextPreset"),mix=uniform("u_blend");
    GLint tick=uniform("u_tick"),breath=uniform("u_breath"),age=uniform("u_age"),spectrum=uniform("u_bands[0]");
    glUniform2f(res,width,height);glUniform1f(strength,response);glUniform1f(uniform("u_shade"),shade);glUniform1f(uniform("u_motion"),1.f);
    GLuint artTexture=0;
    if(argc==9){
      std::ifstream scene(argv[7]);int aw,ah,surfaces;float duration;
      if(!(scene>>aw>>ah>>surfaces>>duration)||aw<16||ah<16||aw>8192||ah>8192||surfaces<1||surfaces>3||!std::isfinite(duration)||duration<=0)throw std::runtime_error("Invalid artwork metadata");
      std::ifstream raw(argv[8],std::ios::binary);std::vector<unsigned char> art((size_t)aw*ah*3);
      if(!raw.read((char*)art.data(),art.size())||raw.peek()!=EOF)throw std::runtime_error("Artwork pixels do not match dimensions");
      glGenTextures(1,&artTexture);glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,artTexture);glPixelStorei(GL_UNPACK_ALIGNMENT,1);
      glTexImage2D(GL_TEXTURE_2D,0,GL_RGB8,aw,ah,0,GL_RGB,GL_UNSIGNED_BYTE,art.data());
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
      glUniform1i(uniform("u_artwork"),0);glUniform1i(uniform("u_surfaceCount"),surfaces);glUniform1f(uniform("u_duration"),duration);
      for(int i=0;i<surfaces;i++){
        float h[9],style[4],color[3],accent[3];
        for(float& v:h)if(!(scene>>v)||!std::isfinite(v))throw std::runtime_error("Invalid surface transform");
        for(float& v:style)if(!(scene>>v)||!std::isfinite(v))throw std::runtime_error("Invalid surface style");
        for(float& v:color)if(!(scene>>v)||!std::isfinite(v))throw std::runtime_error("Invalid surface color");
        for(float& v:accent)if(!(scene>>v)||!std::isfinite(v))throw std::runtime_error("Invalid surface accent");
        auto u=[&](const char* name){return uniform((std::string(name)+"["+std::to_string(i)+"]").c_str());};
        glUniformMatrix3fv(u("u_homography"),1,GL_FALSE,h);glUniform4fv(u("u_surfaceStyle"),1,style);glUniform3fv(u("u_color"),1,color);glUniform3fv(u("u_accent"),1,accent);
      }
    }
    std::ifstream input(argv[2]);if(!input)throw std::runtime_error("Cannot read frame table");
    std::vector<unsigned char> pixels(width*height*3);std::string line;int frame=0;
    auto began=std::chrono::steady_clock::now();
    while(std::getline(input,line)) {
      if(line.empty()||line[0]=='#')continue;
      std::replace(line.begin(),line.end(),',',' ');std::istringstream row(line);
      float time,bass,mid,treble,onset,energy,blend;int preset,next;
      if(!(row>>time>>bass>>mid>>treble>>onset>>energy>>preset>>next>>blend))throw std::runtime_error("Invalid frame row "+std::to_string(frame));
      if(preset<0||preset>8||next<0||next>8)throw std::runtime_error("Preset id outside collection");
      glUniform1f(tim,time);glUniform4f(snd,bass,mid,treble,onset);glUniform1f(eng,energy);
      glUniform1i(pre,preset);glUniform1i(nxt,next);glUniform1f(mix,blend);
      if(preset==8){float t,b,a,bands[24];if(!(row>>t>>b>>a))throw std::runtime_error("Missing song envelopes");for(float& v:bands)if(!(row>>v))throw std::runtime_error("Missing spectral bands");glUniform1f(tick,t);glUniform1f(breath,b);glUniform1f(age,a);glUniform1fv(spectrum,24,bands);}
      glDrawArrays(GL_TRIANGLES,0,3);glReadPixels(0,0,width,height,GL_RGB,GL_UNSIGNED_BYTE,pixels.data());
      auto err=glGetError();if(err!=GL_NO_ERROR)throw std::runtime_error("OpenGL error "+std::to_string(err));
      if(std::fwrite(pixels.data(),1,pixels.size(),stdout)!=pixels.size())throw std::runtime_error("Output pipe closed");
      frame++;
      if(frame%24==0){float seconds=std::chrono::duration<float>(std::chrono::steady_clock::now()-began).count();std::cerr<<"Rendered "<<frame<<" frames ("<<frame/seconds<<" fps)\n";}
    }
    std::fflush(stdout);float seconds=std::chrono::duration<float>(std::chrono::steady_clock::now()-began).count();
    std::cerr<<"Complete: "<<frame<<" frames in "<<seconds<<" seconds\n";
    if(artTexture)glDeleteTextures(1,&artTexture);glDeleteTextures(1,&texture);glDeleteFramebuffers(1,&fbo);glDeleteVertexArrays(1,&vao);glDeleteProgram(program);CGLSetCurrentContext(nullptr);CGLDestroyContext(context);
    return 0;
  }catch(const std::exception& e){std::cerr<<"Visualizer render failed: "<<e.what()<<"\n";return 1;}
}
