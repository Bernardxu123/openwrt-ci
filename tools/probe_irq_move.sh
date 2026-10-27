#!/bin/sh
echo "=== BEFORE ==="
for irq in 19 23 27 53 54; do
  echo "  irq $irq list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) eff_list=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)] eff_hex=$(cat /proc/irq/$irq/effective_affinity 2>/dev/null)"
done
cp /proc/interrupts /tmp/irq_before.txt

echo
echo "=== TRY: irq27 -> cpu1, irq53 -> cpu2, irq23 -> cpu3 ==="
echo 2 > /proc/irq/27/smp_affinity_list 2>/tmp/e1 || echo "  write irq27 failed: $(cat /tmp/e1)"
echo 4 > /proc/irq/53/smp_affinity_list 2>/tmp/e2 || echo "  write irq53 failed: $(cat /tmp/e2)"
echo 8 > /proc/irq/23/smp_affinity_list 2>/tmp/e3 || echo "  write irq23 failed: $(cat /tmp/e3)"

echo "=== AFTER WRITE ==="
for irq in 19 23 27 53 54; do
  echo "  irq $irq list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) eff_list=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)] eff_hex=$(cat /proc/irq/$irq/effective_affinity 2>/dev/null)"
done

echo
echo "=== 6s IRQ counter movement ==="
sleep 6
cp /proc/interrupts /tmp/irq_after.txt
awk '
FNR==NR { for(i=1;i<=NF;i++){ if($i ~ /^[0-9]+$/) b[FILENAME,i]=$i } ; next }
{ for(i=1;i<=NF;i++){ if($i ~ /^[0-9]+$/) { d=$i-b[FILENAME,i]; if(d>0) printf "  %-55s cpu%d +%d\n", $0 ~ /^$/ ? "" : "", i-2, d } } }
' /tmp/irq_before.txt /tmp/irq_after.txt 2>/dev/null | head -5
echo "--- direct compare of key lines ---"
for irq in 19 23 27 53 54; do
  b=$(grep "^ *$irq:" /tmp/irq_before.txt | awk '{print $2,$3,$4,$5}')
  a=$(grep "^ *$irq:" /tmp/irq_after.txt | awk '{print $2,$3,$4,$5}')
  echo "  irq $irq before=[$b] after=[$a]"
done

echo
echo "=== RESTORE ==="
for irq in 19 23 27 53 54; do echo 15 > /proc/irq/$irq/smp_affinity_list 2>/dev/null; done
for irq in 19 23 27 53 54; do
  echo "  irq $irq list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) eff_list=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)]"
done
