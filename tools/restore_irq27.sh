#!/bin/sh
echo "=== current ==="
for irq in 19 23 27 53 54; do
  echo "  irq $irq list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)]"
done
echo "=== restore irq27 -> 0-3 (mask f) ==="
echo f > /proc/irq/27/smp_affinity_list; echo "  rc=$?"
echo "=== verify ==="
for irq in 19 23 27 53 54; do
  echo "  irq $irq list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)]"
done
