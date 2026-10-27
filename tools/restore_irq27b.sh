#!/bin/sh
echo "=== try '0-3' list format ==="
echo "0-3" > /proc/irq/27/smp_affinity_list; echo "  rc=$?  now=$(cat /proc/irq/27/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/27/effective_affinity_list 2>/dev/null)]"
echo "=== try hex 'f' ==="
echo "f" > /proc/irq/27/smp_affinity_list; echo "  rc=$?  now=$(cat /proc/irq/27/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/27/effective_affinity_list 2>/dev/null)]"
echo "=== try '0' ==="
echo "0" > /proc/irq/27/smp_affinity_list; echo "  rc=$?  now=$(cat /proc/irq/27/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/27/effective_affinity_list 2>/dev/null)]"
echo "=== try '0-3' again ==="
echo "0-3" > /proc/irq/27/smp_affinity_list; echo "  rc=$?  now=$(cat /proc/irq/27/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/27/effective_affinity_list 2>/dev/null)]"
echo
echo "=== final state of all ==="
for irq in 19 23 27 53 54; do
  echo "  irq $irq list=$(cat /proc/irq/$irq/smp_affinity_list 2>/dev/null) eff=[$(cat /proc/irq/$irq/effective_affinity_list 2>/dev/null)]"
done
