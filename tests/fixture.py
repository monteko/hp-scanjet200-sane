import signal, struct, sys, time
signal.signal(signal.SIGINT, lambda *a: sys.exit(130))
x,y,w,h=map(int,sys.argv[1:5]); channels=1 if sys.argv[5]=='Gray' else 3
# Tall selections permit cancellation testing without a USB scanner.
if h>3000: time.sleep(5)
sys.stdout.buffer.write(struct.pack('<4sIII', b'SJ20',w,h,channels))
row=bytes((i%251 for i in range(w*channels)))
for _ in range(h): sys.stdout.buffer.write(row)
