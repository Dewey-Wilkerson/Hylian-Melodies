// M3 link check: the runtime symbols generated code needs, as stubs. Linking all generated objects plus this
// file with -Wl,--no-undefined proves the lifted modules have no unresolved symbols.
#include <stdlib.h>
#include "cpu.h"
volatile int g_fnprof;
void fnprof_hit(uint64_t a, uint64_t lr, uint64_t x0) { (void)a; (void)lr; (void)x0; }
void rt_dispatch(Cpu *c) { (void)c; abort(); }
int rt_hook(Cpu *c, uint64_t site) { (void)c; (void)site; return 0; }
void rt_svc(Cpu *c, uint32_t imm, uint64_t pc) { (void)c; (void)imm; (void)pc; abort(); }
void rt_brk(Cpu *c, uint32_t imm, uint64_t pc) { (void)c; (void)imm; (void)pc; abort(); }
void rt_udf(Cpu *c, uint64_t pc) { (void)c; (void)pc; abort(); }
uint64_t rt_ticks(void) { return 0; }
void rt_jt_miss(Cpu *c, uint64_t pc) { (void)c; (void)pc; abort(); }
