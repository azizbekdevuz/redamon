'use client'

import { useState } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { Toggle } from '@/components/ui'
import type { Project } from '@prisma/client'
import styles from '../ProjectForm.module.css'
import { NodeInfoTooltip } from '../NodeInfoTooltip'
import { SECTION_NODE_MAP } from '../nodeMapping'
import { TimeEstimate } from '../TimeEstimate'

type FormData = Omit<Project, 'id' | 'userId' | 'createdAt' | 'updatedAt' | 'user'>

interface SubdomainDiscoverySectionProps {
  data: FormData
  updateField: <K extends keyof FormData>(field: K, value: FormData[K]) => void
}

export function SubdomainDiscoverySection({ data, updateField }: SubdomainDiscoverySectionProps) {
  const [isOpen, setIsOpen] = useState(true)

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader} onClick={() => setIsOpen(!isOpen)}>
        <h2 className={styles.sectionTitle}>
          <Search size={16} />
          Subdomain Discovery
          <NodeInfoTooltip nodes={SECTION_NODE_MAP.SubdomainDiscovery} />
        </h2>
        <ChevronDown
          size={16}
          className={`${styles.sectionIcon} ${isOpen ? styles.sectionIconOpen : ''}`}
        />
      </div>

      {isOpen && (
        <div className={styles.sectionContent}>
          <p className={styles.sectionDescription}>
            Configure which subdomain discovery sources to use. Passive sources query external
            databases without touching the target. Active discovery sends DNS queries directly.
          </p>

          <div className={styles.subSection}>
            <h3 className={styles.subSectionTitle}>Sources <span className={styles.badgePassive}>Passive</span></h3>

            <div className={styles.toggleRow}>
              <div>
                <span className={styles.toggleLabel}>crt.sh</span>
                <p className={styles.toggleDescription}>
                  Certificate transparency logs — discovers subdomains from SSL/TLS certificates
                </p>
              </div>
              <Toggle
                checked={data.crtshEnabled}
                onChange={(checked) => updateField('crtshEnabled', checked)}
              />
            </div>
            {data.crtshEnabled && (
              <div className={styles.fieldRow}>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Max Results</label>
                  <input
                    type="number"
                    className="textInput"
                    value={data.crtshMaxResults}
                    onChange={(e) => updateField('crtshMaxResults', parseInt(e.target.value) || 5000)}
                    min={1}
                    max={50000}
                  />
                  <span className={styles.fieldHint}>Maximum subdomains to collect from crt.sh</span>
                </div>
              </div>
            )}

            <div className={styles.toggleRow}>
              <div>
                <span className={styles.toggleLabel}>HackerTarget</span>
                <p className={styles.toggleDescription}>
                  DNS lookup database — discovers subdomains from HackerTarget&apos;s host search API
                </p>
              </div>
              <Toggle
                checked={data.hackerTargetEnabled}
                onChange={(checked) => updateField('hackerTargetEnabled', checked)}
              />
            </div>
            {data.hackerTargetEnabled && (
              <div className={styles.fieldRow}>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Max Results</label>
                  <input
                    type="number"
                    className="textInput"
                    value={data.hackerTargetMaxResults}
                    onChange={(e) => updateField('hackerTargetMaxResults', parseInt(e.target.value) || 5000)}
                    min={1}
                    max={50000}
                  />
                  <span className={styles.fieldHint}>Maximum subdomains to collect from HackerTarget</span>
                </div>
              </div>
            )}

            <div className={styles.toggleRow}>
              <div>
                <span className={styles.toggleLabel}>Knockpy Recon</span>
                <p className={styles.toggleDescription}>
                  Passive wordlist-based subdomain enumeration using Knockpy&apos;s recon mode
                </p>
              </div>
              <Toggle
                checked={data.knockpyReconEnabled}
                onChange={(checked) => updateField('knockpyReconEnabled', checked)}
              />
            </div>
            {data.knockpyReconEnabled && (
              <div className={styles.fieldRow}>
                <div className={styles.fieldGroup}>
                  <label className={styles.fieldLabel}>Max Results</label>
                  <input
                    type="number"
                    className="textInput"
                    value={data.knockpyReconMaxResults}
                    onChange={(e) => updateField('knockpyReconMaxResults', parseInt(e.target.value) || 5000)}
                    min={1}
                    max={50000}
                  />
                  <span className={styles.fieldHint}>Maximum subdomains to collect from Knockpy</span>
                </div>
              </div>
            )}
          </div>

          <div className={styles.subSection}>
            <h3 className={styles.subSectionTitle}>Discovery <span className={styles.badgeActive}>Active</span></h3>

            <div className={styles.toggleRow}>
              <div>
                <span className={styles.toggleLabel}>Knockpy Bruteforce Mode</span>
                <p className={styles.toggleDescription}>
                  Use wordlist-based subdomain bruteforcing — sends thousands of DNS queries
                </p>
                <TimeEstimate estimate="+5-30 min depending on wordlist size" />
              </div>
              <Toggle
                checked={data.useBruteforceForSubdomains}
                onChange={(checked) => updateField('useBruteforceForSubdomains', checked)}
              />
            </div>
          </div>

          <div className={styles.subSection}>
            <h3 className={styles.subSectionTitle}>DNS Settings <span className={styles.badgePassive}>Passive</span></h3>
            <div className={styles.fieldRow}>
              <div className={styles.fieldGroup}>
                <label className={styles.fieldLabel}>WHOIS Max Retries</label>
                <input
                  type="number"
                  className="textInput"
                  value={data.whoisMaxRetries}
                  onChange={(e) => updateField('whoisMaxRetries', parseInt(e.target.value) || 6)}
                  min={1}
                  max={20}
                />
              </div>
              <div className={styles.fieldGroup}>
                <label className={styles.fieldLabel}>DNS Max Retries</label>
                <input
                  type="number"
                  className="textInput"
                  value={data.dnsMaxRetries}
                  onChange={(e) => updateField('dnsMaxRetries', parseInt(e.target.value) || 3)}
                  min={1}
                  max={10}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
