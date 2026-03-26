'use client'

import { useState } from 'react'
import { ChevronDown, Radar } from 'lucide-react'
import { Toggle } from '@/components/ui'
import type { Project } from '@prisma/client'
import styles from '../ProjectForm.module.css'
import { NodeInfoTooltip } from '../NodeInfoTooltip'
import { TimeEstimate } from '../TimeEstimate'

type FormData = Omit<Project, 'id' | 'userId' | 'createdAt' | 'updatedAt' | 'user'>

interface MasscanSectionProps {
  data: FormData
  updateField: <K extends keyof FormData>(field: K, value: FormData[K]) => void
}

export function MasscanSection({ data, updateField }: MasscanSectionProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader} onClick={() => setIsOpen(!isOpen)}>
        <h2 className={styles.sectionTitle}>
          <Radar size={16} />
          Masscan Port Scanner
          <NodeInfoTooltip section="Masscan" />
          {data.masscanEnabled ? (
            <span className={styles.badgeActive}>Active</span>
          ) : (
            <span className={styles.badgeInactive}>Disabled</span>
          )}
        </h2>
        <ChevronDown
          size={16}
          className={`${styles.sectionIcon} ${isOpen ? styles.sectionIconOpen : ''}`}
        />
      </div>

      {isOpen && (
        <div className={styles.sectionContent}>
          <p className={styles.sectionDescription}>
            High-speed SYN port scanner optimized for large networks and IP/CIDR ranges.
            Uses raw packets for maximum speed. Requires root or CAP_NET_RAW.
            Incompatible with Tor (raw SYN packets bypass TCP stack).
          </p>

          <div className={styles.toggleRow}>
            <div>
              <span className={styles.toggleLabel}>Enable Masscan</span>
              <p className={styles.toggleDescription}>Run Masscan alongside Naabu during port scanning. Results are merged and deduplicated.</p>
            </div>
            <Toggle
              checked={data.masscanEnabled}
              onChange={(checked) => updateField('masscanEnabled', checked)}
            />
          </div>

          <div className={styles.fieldRow}>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Top Ports</label>
              <input
                type="text"
                className="textInput"
                value={data.masscanTopPorts}
                onChange={(e) => updateField('masscanTopPorts', e.target.value)}
                placeholder="1000"
                disabled={!data.masscanEnabled}
              />
              <span className={styles.fieldHint}>Use &ldquo;100&rdquo;, &ldquo;1000&rdquo;, or &ldquo;full&rdquo; for all 65535 ports</span>
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Custom Ports</label>
              <input
                type="text"
                className="textInput"
                value={data.masscanCustomPorts}
                onChange={(e) => updateField('masscanCustomPorts', e.target.value)}
                placeholder="80,443,8080-8090"
                disabled={!data.masscanEnabled}
              />
              <span className={styles.fieldHint}>Overrides Top Ports if set. Use ranges: 8080-8090</span>
            </div>
          </div>

          <div className={styles.fieldRow}>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Rate (packets/sec)</label>
              <input
                type="number"
                className="textInput"
                value={data.masscanRate}
                onChange={(e) => updateField('masscanRate', parseInt(e.target.value) || 1000)}
                min={1}
                disabled={!data.masscanEnabled}
              />
              <span className={styles.fieldHint}>Packets/sec. Masscan can handle very high rates (10k+)</span>
              <TimeEstimate estimate="1000: safe default | 10000+: fast but may overwhelm targets" />
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Wait (seconds)</label>
              <input
                type="number"
                className="textInput"
                value={data.masscanWait}
                onChange={(e) => updateField('masscanWait', parseInt(e.target.value) || 10)}
                min={0}
                disabled={!data.masscanEnabled}
              />
              <span className={styles.fieldHint}>Seconds to wait for late responses after scan completes</span>
            </div>
          </div>

          <div className={styles.fieldRow}>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Retries</label>
              <input
                type="number"
                className="textInput"
                value={data.masscanRetries}
                onChange={(e) => updateField('masscanRetries', parseInt(e.target.value) || 1)}
                min={0}
                max={10}
                disabled={!data.masscanEnabled}
              />
              <span className={styles.fieldHint}>Retry attempts for unresponsive ports</span>
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.fieldLabel}>Exclude Targets</label>
              <input
                type="text"
                className="textInput"
                value={data.masscanExcludeTargets}
                onChange={(e) => updateField('masscanExcludeTargets', e.target.value)}
                placeholder="10.0.0.1, 192.168.0.0/24"
                disabled={!data.masscanEnabled}
              />
              <span className={styles.fieldHint}>Comma-separated IPs/CIDRs to exclude from scanning</span>
            </div>
          </div>

          <div className={styles.toggleRow}>
            <div>
              <span className={styles.toggleLabel}>Banner Grabbing</span>
              <p className={styles.toggleDescription}>Capture service banners (SSH, HTTP, etc.). Increases scan time but provides richer data.</p>
            </div>
            <Toggle
              checked={data.masscanBanners}
              onChange={(checked) => updateField('masscanBanners', checked)}
              disabled={!data.masscanEnabled}
            />
          </div>
        </div>
      )}
    </div>
  )
}
