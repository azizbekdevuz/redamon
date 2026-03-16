'use client'

import { Waypoints } from 'lucide-react'
import { Tooltip } from '@/components/ui'
import styles from './ProjectForm.module.css'

interface NodeInfoTooltipProps {
  nodes: string[]
}

export function NodeInfoTooltip({ nodes }: NodeInfoTooltipProps) {
  if (!nodes.length) return null

  const content = (
    <div className={styles.nodeInfoContent}>
      <span className={styles.nodeInfoLabel}>Graph Nodes</span>
      <div className={styles.nodeInfoPills}>
        {nodes.map(node => (
          <span key={node} className={styles.nodeInfoPill}>{node}</span>
        ))}
      </div>
    </div>
  )

  return (
    <Tooltip content={content} position="bottom" delay={150}>
      <Waypoints size={13} className={styles.nodeInfoIcon} />
    </Tooltip>
  )
}
