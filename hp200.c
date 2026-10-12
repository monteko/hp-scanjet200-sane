#define _POSIX_C_SOURCE 200809L
#include <sane/sane.h>
#include <sane/saneopts.h>
#include <libusb-1.0/libusb.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#ifndef HP200_BRIDGE
#define HP200_BRIDGE "/usr/local/share/hp200-sane/sane_bridge.py"
#endif
#define NOPT 7
#define PX 2486
#define PY 3508
typedef struct {
 SANE_Option_Descriptor opt[NOPT];
 SANE_Word geo[4];
 char mode[16];
 int fd, pid, active, eof;
 volatile sig_atomic_t cancelled;
 size_t remaining;
 SANE_Parameters params;
} Session;
static Session *opened;
static SANE_Device device={"usb", "HP", "Scanjet 200 (experimental)", "flatbed scanner"};
static const SANE_Device *devices[]={&device,NULL};
static const SANE_Device *empty[]={NULL};
static const SANE_String_Const modes[]={"Color","Gray",NULL};
static const SANE_Word resolutions[]={1,300};
static const SANE_Range xr={0,SANE_FIX(210.0),0}, yr={0,SANE_FIX(297.0),0};
static int available(void) {
#ifdef HP200_TEST
 return 1;
#else
 libusb_context *ctx=NULL; libusb_device **list=NULL; int found=0;
 if(libusb_init(&ctx)) return 0;
 ssize_t n=libusb_get_device_list(ctx,&list);
 for(ssize_t i=0;i<n;i++) { struct libusb_device_descriptor d;
  if(!libusb_get_device_descriptor(list[i],&d) && d.idVendor==0x03f0 && d.idProduct==0x1c05) {found=1;break;}}
 if(list) libusb_free_device_list(list,1);
 libusb_exit(ctx); return found;
#endif
}
static int valid(Session *s){return s && s==opened;}
static int pix(SANE_Word v, int total, double mm){return (int)floor(SANE_UNFIX(v)*total/mm+.5);}
static void parameters(Session *s) {
 int x=pix(s->geo[0],PX,210), y=pix(s->geo[1],PY,297);
 int w=pix(s->geo[2],PX,210)-x,h=pix(s->geo[3],PY,297)-y;
 s->params.format=!strcmp(s->mode,"Gray")?SANE_FRAME_GRAY:SANE_FRAME_RGB;
 s->params.last_frame=SANE_TRUE; s->params.depth=8;
 s->params.pixels_per_line=w; s->params.lines=h;
 s->params.bytes_per_line=w*(s->params.format==SANE_FRAME_GRAY?1:3);
}
static void reap(Session *s, int block) {
 if(s->pid>0) {int status; pid_t r;
  do {r=waitpid(s->pid,&status,block?0:WNOHANG);}while(r<0 && errno==EINTR);
  if(r==s->pid || (r<0 && errno==ECHILD)) s->pid=0;
 }
}
SANE_Status sane_hp200_init(SANE_Int *v,SANE_Auth_Callback auth){(void)auth;if(v)*v=SANE_VERSION_CODE(1,0,1);return SANE_STATUS_GOOD;}
void sane_hp200_cancel(SANE_Handle h){Session*s=h;if(!valid(s))return;s->cancelled=1;if(s->pid>0)kill(s->pid,SIGINT);}
void sane_hp200_close(SANE_Handle h){Session*s=h;if(!valid(s))return;if(s->pid>0)sane_hp200_cancel(h);
 if(s->fd>=0) { close(s->fd); }
 reap(s,1);opened=NULL;free(s);}
void sane_hp200_exit(void){if(opened)sane_hp200_close(opened);}
SANE_Status sane_hp200_get_devices(const SANE_Device ***out,SANE_Bool local){(void)local;if(!out)return SANE_STATUS_INVAL;*out=available()?devices:empty;return SANE_STATUS_GOOD;}
SANE_Status sane_hp200_open(SANE_String_Const name,SANE_Handle *h){
 if(!h || !name || (name[0] && strcmp(name,"usb")))return SANE_STATUS_INVAL;
 if(opened)return SANE_STATUS_DEVICE_BUSY;
 if(!available())return SANE_STATUS_INVAL;
 Session*s=calloc(1,sizeof(*s));if(!s)return SANE_STATUS_NO_MEM;
 s->fd=-1;strcpy(s->mode,"Color");s->geo[2]=SANE_FIX(210);s->geo[3]=SANE_FIX(297);
 const char* names[]={SANE_NAME_NUM_OPTIONS,SANE_NAME_SCAN_MODE,SANE_NAME_SCAN_RESOLUTION,SANE_NAME_SCAN_TL_X,SANE_NAME_SCAN_TL_Y,SANE_NAME_SCAN_BR_X,SANE_NAME_SCAN_BR_Y};
 const char* titles[]={"Number of options","Scan mode","Resolution","Top-left x","Top-left y","Bottom-right x","Bottom-right y"};
 for(int i=0;i<NOPT;i++){s->opt[i].name=names[i];s->opt[i].title=titles[i];s->opt[i].desc=titles[i];s->opt[i].size=sizeof(SANE_Word);s->opt[i].cap=SANE_CAP_SOFT_SELECT|SANE_CAP_SOFT_DETECT;}
 s->opt[0].type=SANE_TYPE_INT;s->opt[0].cap=SANE_CAP_SOFT_DETECT;
 s->opt[1].type=SANE_TYPE_STRING;s->opt[1].size=sizeof(s->mode);s->opt[1].constraint_type=SANE_CONSTRAINT_STRING_LIST;s->opt[1].constraint.string_list=modes;
 s->opt[2].type=SANE_TYPE_INT;s->opt[2].unit=SANE_UNIT_DPI;s->opt[2].constraint_type=SANE_CONSTRAINT_WORD_LIST;s->opt[2].constraint.word_list=resolutions;
 for(int i=3;i<=6;i++){s->opt[i].type=SANE_TYPE_FIXED;s->opt[i].unit=SANE_UNIT_MM;s->opt[i].constraint_type=SANE_CONSTRAINT_RANGE;s->opt[i].constraint.range=((i-3)%2)?&yr:&xr;}
 opened=s;parameters(s);*h=s;return SANE_STATUS_GOOD;
}
const SANE_Option_Descriptor *sane_hp200_get_option_descriptor(SANE_Handle h,SANE_Int i){Session*s=h;return valid(s)&&i>=0&&i<NOPT?&s->opt[i]:NULL;}
SANE_Status sane_hp200_control_option(SANE_Handle h,SANE_Int i,SANE_Action action,void*value,SANE_Int*info){
 Session*s=h;if(info)*info=0;if(!valid(s)||!value||i<0||i>=7)return SANE_STATUS_INVAL;
 if(action==SANE_ACTION_GET_VALUE){if(i==0)*(SANE_Word*)value=NOPT;else if(i==1)strcpy(value,s->mode);else if(i==2)*(SANE_Word*)value=300;else *(SANE_Word*)value=s->geo[i-3];return SANE_STATUS_GOOD;}
 if(action!=SANE_ACTION_SET_VALUE||i==0)return SANE_STATUS_INVAL;
 reap(s,0);if((s->active&&!s->cancelled)||s->pid>0)return SANE_STATUS_DEVICE_BUSY;
 if(i==1){if(strcmp(value,"Color")&&strcmp(value,"Gray"))return SANE_STATUS_INVAL;strcpy(s->mode,value);}
 else if(i==2){if(*(SANE_Word*)value!=300){*(SANE_Word*)value=300;if(info)*info|=SANE_INFO_INEXACT;}}
 else {SANE_Word v=*(SANE_Word*)value;const SANE_Range*r=s->opt[i].constraint.range;
 if(v<r->min||v>r->max)return SANE_STATUS_INVAL;
 s->geo[i-3]=v;}
 parameters(s);if(info)*info|=SANE_INFO_RELOAD_PARAMS;return SANE_STATUS_GOOD;
}
SANE_Status sane_hp200_get_parameters(SANE_Handle h,SANE_Parameters*p){Session*s=h;if(!valid(s)||!p)return SANE_STATUS_INVAL;parameters(s);*p=s->params;return SANE_STATUS_GOOD;}
static SANE_Status read_bytes(Session*s,unsigned char*buf,int max,int*got){
 *got=0;for(;;){if(s->cancelled)return SANE_STATUS_CANCELLED;
 struct pollfd p={s->fd,POLLIN,0};int r=poll(&p,1,100);
 if(r<0){if(errno==EINTR)continue;return SANE_STATUS_IO_ERROR;}if(!r)continue;
 ssize_t n=read(s->fd,buf,(size_t)max);if(n<0){if(errno==EINTR)continue;return SANE_STATUS_IO_ERROR;}
 if(n==0)return SANE_STATUS_EOF;
 *got=(int)n;return SANE_STATUS_GOOD;}
}
SANE_Status sane_hp200_start(SANE_Handle h){
 Session*s=h;if(!valid(s))return SANE_STATUS_INVAL;reap(s,0);
 if((s->active&&!s->cancelled)||s->pid>0)return SANE_STATUS_DEVICE_BUSY;
 if(s->fd>=0){close(s->fd);s->fd=-1;}parameters(s);
 if(s->params.pixels_per_line<1||s->params.lines<1)return SANE_STATUS_INVAL;
 int pipefd[2];if(pipe(pipefd))return SANE_STATUS_IO_ERROR;
 fcntl(pipefd[0],F_SETFD,FD_CLOEXEC);fcntl(pipefd[1],F_SETFD,FD_CLOEXEC);
 char x[24],y[24],w[24],height[24];
 snprintf(x,sizeof x,"%d",pix(s->geo[0],PX,210));snprintf(y,sizeof y,"%d",pix(s->geo[1],PY,297));
 snprintf(w,sizeof w,"%d",s->params.pixels_per_line);snprintf(height,sizeof height,"%d",s->params.lines);
 s->cancelled=0;s->eof=0;s->active=1;
 pid_t pid=fork();if(pid<0){close(pipefd[0]);close(pipefd[1]);s->active=0;return SANE_STATUS_IO_ERROR;}
 if(pid==0){close(pipefd[0]);if(dup2(pipefd[1],STDOUT_FILENO)<0)_exit(127);close(pipefd[1]);
  execl("/usr/bin/python3","python3",HP200_BRIDGE,x,y,w,height,s->mode,(char*)NULL);_exit(127);}
 s->pid=pid;s->fd=pipefd[0];close(pipefd[1]);
 unsigned char header[16];int have=0;
 while(have<16){int n;SANE_Status rc=read_bytes(s,header+have,16-have,&n);if(rc!=SANE_STATUS_GOOD){s->active=0;return rc==SANE_STATUS_EOF?SANE_STATUS_IO_ERROR:rc;}have+=n;}
 uint32_t vals[3]={0};for(int j=0;j<3;j++)for(int k=0;k<4;k++)vals[j]|=(uint32_t)header[4+j*4+k]<<(k*8);
 if(memcmp(header,"SJ20",4)||vals[0]!=(uint32_t)s->params.pixels_per_line||vals[1]!=(uint32_t)s->params.lines||vals[2]!=(uint32_t)(s->params.format==SANE_FRAME_GRAY?1:3)){
  sane_hp200_cancel(s);s->active=0;return SANE_STATUS_IO_ERROR;}
 s->remaining=(size_t)s->params.bytes_per_line*s->params.lines;return SANE_STATUS_GOOD;
}
SANE_Status sane_hp200_read(SANE_Handle h,SANE_Byte*buf,SANE_Int max,SANE_Int*len){
 Session*s=h;if(len)*len=0;if(!valid(s)||!buf||!len||max<=0)return SANE_STATUS_INVAL;
 if(s->cancelled){s->active=0;return SANE_STATUS_CANCELLED;}if(s->eof)return SANE_STATUS_EOF;if(!s->active)return SANE_STATUS_INVAL;
 if(!s->remaining){s->active=0;s->eof=1;close(s->fd);s->fd=-1;reap(s,1);return SANE_STATUS_EOF;}
 if((size_t)max>s->remaining)max=(SANE_Int)s->remaining;
 SANE_Status rc=read_bytes(s,buf,max,len);if(rc==SANE_STATUS_GOOD)s->remaining-=(size_t)*len;
 else {s->active=0;if(rc==SANE_STATUS_EOF)rc=SANE_STATUS_IO_ERROR;}return rc;
}
SANE_Status sane_hp200_set_io_mode(SANE_Handle h,SANE_Bool nb){Session*s=h;if(!valid(s))return SANE_STATUS_INVAL;return nb?SANE_STATUS_UNSUPPORTED:SANE_STATUS_GOOD;}
SANE_Status sane_hp200_get_select_fd(SANE_Handle h,SANE_Int*fd){(void)fd;return valid(h)?SANE_STATUS_UNSUPPORTED:SANE_STATUS_INVAL;}
