"""Сборка PDF из редактируемых Markdown. Требуется ReportLab только для сборки отчётов."""
from pathlib import Path
import re,json,html,subprocess
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,KeepTogether
from reportlab.graphics.shapes import Drawing,String,Rect
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF,renderSVG
ROOT=Path(__file__).resolve().parents[1];FONT=ROOT/'design/fonts'
for name,file in [('Plex','regular'),('PlexMedium','medium'),('PlexBold','semibold')]:pdfmetrics.registerFont(TTFont(name,str(FONT/f'ibm-plex-sans-{file}.ttf')))
pdfmetrics.registerFontFamily('Plex',normal='Plex',bold='PlexBold',italic='Plex',boldItalic='PlexBold')
ink=colors.HexColor('#192124');muted=colors.HexColor('#58656b');amber=colors.HexColor('#b58115');gray=colors.HexColor('#8c9aa0')
styles={
 'body':ParagraphStyle('body',fontName='Plex',fontSize=10.4,leading=15,textColor=ink,spaceAfter=9,splitLongWords=True),
 'title':ParagraphStyle('title',fontName='PlexBold',fontSize=22,leading=27,textColor=ink,spaceAfter=13),
 'h1':ParagraphStyle('h1',fontName='PlexMedium',fontSize=16,leading=20,textColor=ink,spaceBefore=17,spaceAfter=10,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='PlexMedium',fontSize=12,leading=16,textColor=ink,spaceBefore=12,spaceAfter=8,keepWithNext=True),
 'cell':ParagraphStyle('cell',fontName='Plex',fontSize=8.1,leading=11,textColor=ink,splitLongWords=True),
 'headcell':ParagraphStyle('headcell',fontName='PlexMedium',fontSize=8.1,leading=11,textColor=ink),
 'caption':ParagraphStyle('caption',fontName='Plex',fontSize=9,leading=12,textColor=muted,spaceBefore=5,spaceAfter=12)
}
def inline(s):
    s=html.escape(s.replace('∪',' + ')).replace('—','-').replace('–','-').replace('\u2011','-')
    s=re.sub(r'`([^`]+)`',r'<font name="PlexMedium">\1</font>',s)
    s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1',s)
    return s

def chart(name,title,labels,a,b,ytitle,maximum=None):
    d=Drawing(510,250);d.add(String(2,232,title,fontName='PlexMedium',fontSize=12,fillColor=ink))
    c=VerticalBarChart();c.x=47;c.y=53;c.width=445;c.height=155;c.data=[a,b];c.categoryAxis.categoryNames=labels;c.categoryAxis.labels.fontName='Plex';c.categoryAxis.labels.fontSize=9;c.valueAxis.labels.fontName='Plex';c.valueAxis.labels.fontSize=8;c.valueAxis.valueMin=0
    if maximum:c.valueAxis.valueMax=maximum
    c.bars[0].fillColor=gray;c.bars[1].fillColor=amber;c.bars.strokeColor=None;c.groupSpacing=12;c.barSpacing=2;c.valueAxis.gridStrokeColor=colors.HexColor('#e5e8e9');c.valueAxis.visibleGrid=True;c.categoryAxis.strokeColor=muted;c.valueAxis.strokeColor=muted
    d.add(c);d.add(String(47,215,ytitle,fontName='Plex',fontSize=8,fillColor=muted))
    for x,color,label in [(47,gray,'A: исходный вариант'),(250,amber,'B: исследуемый вариант')]:
        d.add(Rect(x,16,12,8,fillColor=color,strokeColor=None));d.add(String(x+18,15,label,fontName='Plex',fontSize=9,fillColor=ink))
    path=ROOT/f'reports/figures/{name}';renderPDF.drawToFile(d,str(path)+'.pdf');renderSVG.drawToFile(d,str(path)+'.svg');subprocess.run(['pdftoppm','-scale-to','1500','-png','-singlefile',str(path)+'.pdf',str(path)],check=True,stdout=subprocess.DEVNULL)
s=json.loads((ROOT/'reports/figures/chart-data.json').read_text())
conds=['normal','high_load','scarcity','delays'];chart('allocation','Распределение заказов: доля обслуживания',['Обычно','Нагрузка','Дефицит','Задержки'],[s['allocation'][c]['service_rate']['a_mean']*100 for c in conds],[s['allocation'][c]['service_rate']['b_mean']*100 for c in conds],'Проценты; 10 пар на условие',50)
chart('negotiation','Раздельные сравнения: средняя цена завершённых',['Переговоры','Рейтинг'],[float(s[n]['controlled']['final_price']['a_mean']) for n in ['negotiation','rating']],[float(s[n]['controlled']['final_price']['b_mean']) for n in ['negotiation','rating']],'Рубли; 10 пар на исследование',250)
chart('faults','Отказы: сохранение и восстановление обслуживания',[f'F{i}' for i in range(1,8)],[s['faults'][f'F{i}']['service_rate']['a_mean']*100 for i in range(1,8)],[s['faults'][f'F{i}']['service_rate']['b_mean']*100 for i in range(1,8)],'Проценты; 10 пар на тип воздействия',100)

def widths(rows):
    n=len(rows[0]);heads=' '.join(rows[0])
    if n==7:return [54,110,57,57,57,57,62] if 'Показатель' in heads else [32,62,62,62,62,105,69]
    if n==5 and rows[0][0]=='Роль':return [49,76,106,94,129]
    if n==5:return [190,67,67,67,63]
    if n==3 and rows[0][0]=='seq':return [35,70,349]
    if n==3 and rows[0][0]=='Тип':return [28,174,252]
    if n==3:return [232,111,111]
    return [454/n]*n

def footer(canvas,doc):
    canvas.saveState();canvas.setFont('Plex',8);canvas.setFillColor(muted);canvas.drawString(70,32,'Шашечки / Теория многоагентных систем / 2026');canvas.drawRightString(525,32,str(doc.page));canvas.restoreState()
def build(number):
    source=ROOT/f'reports/lab-{number:02}.md';lines=source.read_text().splitlines();story=[];i=0;titlecount=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                r=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch('[-: ]+',x) for x in r):rows.append(r)
                i+=1
            data=[[Paragraph(inline(c),styles['headcell' if k==0 else 'cell']) for c in r] for k,r in enumerate(rows)]
            t=Table(data,colWidths=widths(rows),repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf0f1')),('LINEBELOW',(0,0),(-1,0),.5,gray),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#e5e8e9')),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.extend([t,Spacer(1,12)]);continue
        image=re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)',line)
        if image:
            p=(source.parent/image[2]).resolve();im=Image(str(p));scale=min(454/im.imageWidth,(230 if p.stem=='roles' else 325)/im.imageHeight);im.drawWidth=im.imageWidth*scale;im.drawHeight=im.imageHeight*scale;group=[im,Paragraph(inline(image[1]),styles['caption'])]
            if story and isinstance(story[-1],Paragraph) and story[-1].style.name in {'h1','h2'}:group.insert(0,story.pop())
            story.append(KeepTogether(group));i+=1;continue
        if line.startswith('#'):
            level=len(line)-len(line.lstrip('#'));text=line[level:].strip();kind='title' if level==1 and titlecount<2 else ('h1' if level<=2 else 'h2');titlecount+=level==1;story.append(Paragraph(inline(text),styles[kind]));i+=1;continue
        if re.match(r'^\d+\. ',line):
            story.append(Paragraph(inline(line),styles['body']));i+=1;continue
        paras=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','![')):
            paras.append(lines[i].strip());i+=1
        story.append(Paragraph(inline(' '.join(paras)),styles['body']))
    references=next((j for j,item in enumerate(story) if isinstance(item,Paragraph) and item.text=='Источники и отдельные приложения'),None)
    if references is not None:story=story[:references]+[KeepTogether(story[references:])]
    doc=SimpleDocTemplate(str(ROOT/f'reports/lab-{number:02}.pdf'),pagesize=(595.276,841.89),rightMargin=70,leftMargin=70,topMargin=52,bottomMargin=52,title=f'Шашечки. Лабораторная работа №{number}',author='Учебный проект «Шашечки»',pageCompression=1)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
for n in range(1,5):build(n)
print('Created four PDFs from Markdown')
