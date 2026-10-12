import ctypes as c
from pathlib import Path
import threading, time, unittest
lib=c.CDLL(str(Path('tests/backend-test.so').resolve()))
I=c.c_int; H=c.c_void_p
class Params(c.Structure):
 _fields_=[('format',I),('last',I),('bpl',I),('width',I),('lines',I),('depth',I)]
class Device(c.Structure):
 _fields_=[('name',c.c_char_p),('vendor',c.c_char_p),('model',c.c_char_p),('type',c.c_char_p)]
for name,args in {
 'init':[c.POINTER(I),H], 'get_devices':[c.POINTER(c.POINTER(c.POINTER(Device))),I],
 'open':[c.c_char_p,c.POINTER(H)],'close':[H],'cancel':[H],
 'control_option':[H,I,I,H,c.POINTER(I)],'get_parameters':[H,c.POINTER(Params)],
 'start':[H],'read':[H,H,I,c.POINTER(I)],'set_io_mode':[H,I]
}.items():
 fn=getattr(lib,'sane_hp200_'+name);fn.argtypes=args;fn.restype=None if name in ('close','cancel') else I

class BackendTests(unittest.TestCase):
 def setUp(self):
  self.h=H();self.assertEqual(lib.sane_hp200_init(None,None),0)
  self.assertEqual(lib.sane_hp200_open(b'usb',c.byref(self.h)),0)
 def tearDown(self):lib.sane_hp200_close(self.h)
 def setword(self,i,v):
  val=I(v);info=I();rc=lib.sane_hp200_control_option(self.h,i,1,c.byref(val),c.byref(info))
  self.assertEqual(rc,0);return val.value,info.value
 def test_color_stream_crop_and_repeat(self):
  self.setword(3,10*65536);self.setword(4,5*65536)
  self.setword(5,40*65536);self.setword(6,30*65536)
  p=Params();self.assertEqual(lib.sane_hp200_get_parameters(self.h,c.byref(p)),0)
  self.assertEqual((p.width,p.lines,p.depth),(356,295,8))
  for _ in range(2):
   self.assertEqual(lib.sane_hp200_start(self.h),0)
   data=bytearray();buf=c.create_string_buffer(4093);n=I()
   while True:
    rc=lib.sane_hp200_read(self.h,buf,len(buf),c.byref(n))
    if rc==5:break
    self.assertEqual(rc,0);data.extend(buf.raw[:n.value])
   row=bytes(i%251 for i in range(p.bpl))
   self.assertEqual(bytes(data),row*p.lines)
   lib.sane_hp200_cancel(self.h)
 def test_gray_and_resolution_constraint(self):
  value=c.create_string_buffer(b'Gray');info=I()
  self.assertEqual(lib.sane_hp200_control_option(self.h,1,1,value,c.byref(info)),0)
  self.assertEqual(self.setword(2,600)[0],300)
  self.setword(6,2*65536);p=Params()
  lib.sane_hp200_get_parameters(self.h,c.byref(p))
  self.assertEqual((p.format,p.bpl),(0,2486))
  self.assertEqual(lib.sane_hp200_start(self.h),0)
  lib.sane_hp200_cancel(self.h)
  n=I();buf=c.create_string_buffer(32)
  self.assertEqual(lib.sane_hp200_read(self.h,buf,32,c.byref(n)),2)
 def test_cancel_during_start(self):
  result=[];t=threading.Thread(target=lambda:result.append(lib.sane_hp200_start(self.h)))
  t.start();time.sleep(.3);lib.sane_hp200_cancel(self.h);t.join(2)
  self.assertFalse(t.is_alive());self.assertEqual(result,[2])
 def test_invalid_geometry_and_single_open(self):
  self.setword(3,200*65536);self.setword(5,100*65536)
  self.assertEqual(lib.sane_hp200_start(self.h),4)
  h=H();self.assertEqual(lib.sane_hp200_open(b'usb',c.byref(h)),3)
  self.assertEqual(lib.sane_hp200_set_io_mode(self.h,1),1)

if __name__=='__main__':unittest.main()
