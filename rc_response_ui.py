"""Qt-native analytical RC step-response graphs."""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QSizePolicy
from components import engineering
from simulation.rc import rc_response_phase
import math


class RCPlot(QWidget):
    def __init__(self, timing, initial, final, quantity, parent=None):
        super().__init__(parent)
        self.timing, self.initial, self.final, self.quantity = timing, initial, final, quantity
        self.progress = 0
        self.setFixedHeight(148)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setAccessibleName('Predicted ' + getattr(timing, 'storage_name', 'inductor' if getattr(timing, 'kind', 'RC') == 'RL' else 'capacitor') + ' ' + ('voltage' if quantity == 0 else 'current'))

    def value(self, tau):
        return self.timing.response(tau*self.timing.tau_s, self.initial, self.final)[self.quantity]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#cbd7d4'), 1))
        p.setBrush(QColor('#f7faf9'))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),10,10)
        font=p.font();font.setPixelSize(11);p.setFont(font)
        area=QRectF(57,28,max(24,self.width()-72),92)
        samples = 600 if getattr(self.timing, "kind", "RC") == "RLC" else 100
        values=[self.value(5*i/samples) for i in range(samples+1)]
        bounds = values + ([self.initial, self.final] if self.quantity == getattr(self.timing, "storage_quantity", 0) else [])
        lo,hi=min(0,min(bounds)),max(0,max(bounds))
        if lo==hi:lo,hi=-1,1
        def point(t,v):
            return QPointF(area.left()+t/5*area.width(),area.bottom()-(v-lo)/(hi-lo)*area.height())
        p.setPen(QColor('#263c3f'))
        p.drawText(QRectF(10,6,self.width()-20,18),Qt.AlignmentFlag.AlignLeft,'Voltage' if self.quantity==0 else 'Current (1 → 2)')
        for v in (lo,hi):
            y=point(0,v).y()
            p.setPen(QPen(QColor('#e0e7e5'),1));p.drawLine(QPointF(area.left(),y),QPointF(area.right(),y))
            p.setPen(QColor('#606a68'))
            p.drawText(QRectF(2,y-8,50,16),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,engineering(v,'V' if self.quantity==0 else 'A'))
        ticks = ((0,'0'),(1,'τ'),(5,'5τ'))
        if getattr(self.timing, "kind", "RC") == "RLC":
            ticks = ((0, '0'), (2.5, engineering(self.timing.duration_s/2, 's')), (5, engineering(self.timing.duration_s, 's')))
        for t,label in ticks:
            x=point(t,lo).x()
            p.setPen(QPen(QColor('#ccd7d4'),1,Qt.PenStyle.DashLine));p.drawLine(QPointF(x,area.top()),QPointF(x,area.bottom()))
            p.setPen(QColor('#606a68'));p.drawText(QRectF(x-28,area.bottom()+5,56,18),Qt.AlignmentFlag.AlignCenter,label)
        path=QPainterPath(point(0,values[0]))
        for i,v in enumerate(values[1:],1):path.lineTo(point(5*i/samples,v))
        colour=QColor('#42447a' if self.quantity==0 else '#2878b5')
        p.setPen(QPen(colour,2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawPath(path)
        cursor=point(self.progress,self.value(self.progress))
        p.setPen(QPen(QColor('#869c98'),1,Qt.PenStyle.DotLine));p.drawLine(QPointF(cursor.x(),area.top()),QPointF(cursor.x(),area.bottom()))
        p.setPen(QPen(colour,1));p.setBrush(colour);p.drawEllipse(cursor,3,3)


class RCResponseWidget(QWidget):
    def __init__(self,timing,initial,final,initial_assumed=False,parent=None):
        super().__init__(parent)
        self.timing,self.initial,self.final=timing,initial,final
        self.setObjectName(getattr(timing, 'kind', 'RC').lower() + 'Response')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        title=QLabel('Predicted ' + getattr(timing, 'kind', 'RC') + ' response');title.setStyleSheet('font-weight: 500; color: #42447a; background: transparent;');layout.addWidget(title)
        self.reading=QLabel();self.reading.setWordWrap(True);layout.addWidget(self.reading)
        self.title = title
        self.plots=[RCPlot(timing,initial,final,q,self) for q in (0,1)]
        for plot in self.plots:layout.addWidget(plot)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(0,500)
        self.slider.setAccessibleName('Inspect ' + getattr(timing, 'kind', 'RC') + (' response time' if getattr(timing, 'kind', 'RC') == 'RLC' else ' response time from zero to five time constants'))
        self.slider.setStyleSheet('QSlider { background: transparent; } QSlider::groove:horizontal { height: 4px; background: #cbd7d4; border-radius: 2px; } QSlider::sub-page:horizontal { background: #729b94; } QSlider::handle:horizontal { width: 12px; background: #527f85; border-radius: 6px; margin: -4px 0; }')
        layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self.inspect_time);self.inspect_time(0)

    def inspect_time(self,position):
        tau=position/100;time=tau*self.timing.tau_s
        v,i=self.timing.response(time,self.initial,self.final)
        if getattr(self.timing, "kind", "RC") == "RLC":
            self.reading.setText(f"At t = {engineering(time,'s')}:<br>V = {engineering(v,'V')}, I = {engineering(i,'A')}")
            for plot in self.plots:
                plot.progress = tau
                plot.update()
            return
        phase = rc_response_phase(self.initial, self.final)
        if getattr(self.timing, "kind", "RC") == "RL":
            phase = {"charging": "current rise", "discharging": "current decay"}.get(phase, phase)
        progress = 100 * (1 - math.exp(-tau))
        status = "steady" if phase == "steady" else f"{progress:.1f}% {phase}"
        self.reading.setText(f"At t = {engineering(time,'s')} ({status}):<br>V = {engineering(v,'V')}, I = {engineering(i,'A')}")
        for plot in self.plots:plot.progress=tau;plot.update()
