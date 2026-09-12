"""Classic music-video credits, shared by preview and export."""
import io
import os
from pathlib import Path

def credits_for(plan):
    values=plan.get('credits') or {'artist':plan.get('artist',''),'songTitle':plan.get('title','')}
    return {'enabled':values.get('enabled',True),**{key:values.get(key,'') for key in ('artist','songTitle','recordLabel')}}


def credit_lines(credits):
    if not credits['enabled']:return []
    # Each optional value occupies one line. Empty values add no placeholder.
    return [' '.join(credits[key].split()) for key in ('artist','songTitle','recordLabel') if credits[key].strip()]


def credit_windows(duration):
    start=min(.7,duration*.1);end=max(start,duration-.8)
    spans=[(start,min(7.5,end)),(max(start,duration-8.5),end)]
    result=[]
    for a,b in sorted(spans):
        if b<=a:continue
        if result and a<=result[-1][1]:result[-1]=(result[-1][0],max(result[-1][1],b))
        else:result.append((a,b))
    return result


def credit_font(size):
    from PIL import ImageFont
    configured=os.environ.get('SOUND_VISION_CREDIT_FONT')
    path=Path(configured) if configured else Path(__file__).resolve().parent.parent/'public/fonts/LeagueSpartan.ttf'
    font=ImageFont.truetype(str(path),size)
    if not configured:font.set_variation_by_axes([800])
    return font,{'family':font.getname()[0],'source':'configured-font' if configured else 'open-source-fallback'}


def render_credits(credits):
    from PIL import Image,ImageDraw
    image=Image.new('RGBA',(1920,1080),(0,0,0,0));draw=ImageDraw.Draw(image)
    lines=credit_lines(credits);size=56;font,info=credit_font(size)
    if lines:
        widest=max(draw.textlength(text,font=font) for text in lines)
        if widest>1536:size=max(8,int(size*1536/widest));font,info=credit_font(size)
        # Font hinting can round the estimated width upward on another platform.
        while size>8 and max(draw.textlength(text,font=font) for text in lines)>1536:
            size-=1;font,info=credit_font(size)
        # Keep broadcast-era type scale; adapt the inset to a modern 16:9 frame.
        leading=round(size*1.14);last_baseline=1026;left=128
        for i,text in enumerate(lines):
            y=last_baseline-(len(lines)-1-i)*leading
            draw.text((left+3,y+3),text,font=font,anchor='ls',fill=(0,0,0,245),stroke_width=1,stroke_fill=(0,0,0,220))
            draw.text((left,y),text,font=font,anchor='ls',fill='white')
    info.update(size=size,lines=lines,placement='lower-left',shadowPixels=3,leftPixels=128,lastBaseline=1026)
    return image,info


def preview(credits):
    import base64
    image,info=render_credits(credits);image.thumbnail((768,432))
    output=io.BytesIO();image.save(output,format='PNG')
    return {'image':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),'font':info}
