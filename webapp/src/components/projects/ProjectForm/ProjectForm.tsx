'use client'

import { useState, useEffect, useCallback } from 'react'
import { Save, X, Loader2, AlertTriangle, Download, ShieldAlert } from 'lucide-react'
import type { Project } from '@prisma/client'
import { validateProjectForm } from '@/lib/validation'
import styles from './ProjectForm.module.css'

// Import sections
import { TargetSection } from './sections/TargetSection'
import { ScanModulesSection } from './sections/ScanModulesSection'
import { NaabuSection } from './sections/NaabuSection'
import { HttpxSection } from './sections/HttpxSection'
import { NucleiSection } from './sections/NucleiSection'
import { KatanaSection } from './sections/KatanaSection'
import { GauSection } from './sections/GauSection'
import { KiterunnerSection } from './sections/KiterunnerSection'
import { CveLookupSection } from './sections/CveLookupSection'
import { MitreSection } from './sections/MitreSection'
import { SecurityChecksSection } from './sections/SecurityChecksSection'
import { GithubSection } from './sections/GithubSection'
import { AgentBehaviourSection } from './sections/AgentBehaviourSection'
import { AttackSkillsSection } from './sections/AttackSkillsSection'
import { ShodanSection } from './sections/ShodanSection'
import { UrlscanSection } from './sections/UrlscanSection'
import { SubdomainDiscoverySection } from './sections/SubdomainDiscoverySection'
import { ToolMatrixSection } from './sections/ToolMatrixSection'
import { GvmScanSection } from './sections/GvmScanSection'
import { CypherFixSettingsSection } from './sections/CypherFixSettingsSection'
import { RoeSection } from './sections/RoeSection'

type ProjectFormData = Omit<Project, 'id' | 'userId' | 'createdAt' | 'updatedAt' | 'user'>

interface ConflictResult {
  hasConflict: boolean
  conflictType: 'full_scan_exists' | 'full_scan_requested' | 'subdomain_overlap' | null
  conflictingProject: {
    id: string
    name: string
    targetDomain: string
    subdomainList: string[]
  } | null
  overlappingSubdomains: string[]
  message: string | null
}

interface ProjectFormProps {
  initialData?: Partial<ProjectFormData> & { id?: string }
  onSubmit: (data: ProjectFormData & { roeFile?: File | null }) => Promise<void>
  onCancel: () => void
  isSubmitting?: boolean
  mode: 'create' | 'edit'
}

const TAB_GROUPS = [
  {
    label: 'Scope',
    style: 'tabGroupScope',
    tabs: [
      { id: 'roe', label: 'RoE' },
    ],
  },
  {
    label: 'Recon Pipeline',
    style: 'tabGroupRecon',
    tabs: [
      { id: 'target', label: 'Target & Modules' },
      { id: 'discovery', label: 'Discovery & OSINT' },
      { id: 'port', label: 'Port Scanning' },
      { id: 'http', label: 'HTTP Probing' },
      { id: 'resource', label: 'Resource Enum' },
      { id: 'vuln', label: 'Vulnerability Scanning' },
      { id: 'cve', label: 'CVE & MITRE' },
      { id: 'security', label: 'Security Checks' },
      { id: 'gvm', label: 'GVM Scan' },
      { id: 'integrations', label: 'Integrations', wide: true },
    ],
  },
  {
    label: 'AI Agent',
    style: 'tabGroupAgent',
    tabs: [
      { id: 'agent', label: 'Agent Behaviour' },
      { id: 'toolmatrix', label: 'Tool Matrix' },
      { id: 'attack', label: 'Attack Skills' },
    ],
  },
  {
    label: 'Remediation',
    style: 'tabGroupRemediation',
    tabs: [
      { id: 'cypherfix', label: 'CypherFix' },
    ],
  },
] as const

type TabId = typeof TAB_GROUPS[number]['tabs'][number]['id']

// Minimal fallback defaults - only required fields
// Full defaults are fetched from /api/projects/defaults (served by recon backend)
const MINIMAL_DEFAULTS: Partial<ProjectFormData> = {
  name: '',
  description: '',
  targetDomain: '',
  subdomainList: [],
  ipMode: false,
  targetIps: [],
  scanModules: ['domain_discovery', 'port_scan', 'http_probe', 'resource_enum', 'vuln_scan'],
}

// Fetch defaults from the recon backend (single source of truth)
async function fetchDefaults(): Promise<Partial<ProjectFormData>> {
  try {
    const response = await fetch('/api/projects/defaults')
    if (!response.ok) {
      console.warn('Failed to fetch defaults, using minimal fallback')
      return MINIMAL_DEFAULTS
    }
    const defaults = await response.json()
    // Merge with minimal defaults to ensure required fields exist
    return { ...MINIMAL_DEFAULTS, ...defaults }
  } catch (error) {
    console.warn('Error fetching defaults:', error)
    return MINIMAL_DEFAULTS
  }
}

export function ProjectForm({
  initialData,
  onSubmit,
  onCancel,
  isSubmitting = false,
  mode
}: ProjectFormProps) {
  const [activeTab, setActiveTab] = useState<TabId>('target')
  const [isLoadingDefaults, setIsLoadingDefaults] = useState(mode === 'create')
  const [formData, setFormData] = useState<ProjectFormData>(() => ({
    ...MINIMAL_DEFAULTS,
    ...initialData
  } as ProjectFormData))

  // Domain conflict checking
  const [conflict, setConflict] = useState<ConflictResult | null>(null)
  const [isCheckingConflict, setIsCheckingConflict] = useState(false)

  // Guardrail block modal
  const [guardrailError, setGuardrailError] = useState<string | null>(null)

  // RoE document file (held in memory until project creation)
  const [roeFile, setRoeFile] = useState<File | null>(null)

  // Extract project ID for edit mode (to exclude from conflict check)
  const projectId = (initialData as { id?: string } | undefined)?.id

  // Check for domain conflicts (IP mode skips — tenant-scoped constraints allow overlap)
  const checkConflict = useCallback(async () => {
    // No conflict check needed for IP mode
    if (formData.ipMode) {
      setConflict(null)
      return
    }

    if (!(formData.targetDomain || '').trim()) {
      setConflict(null)
      return
    }

    setIsCheckingConflict(true)
    try {
      const response = await fetch('/api/projects/check-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          targetDomain: formData.targetDomain || '',
          subdomainList: formData.subdomainList || [],
          ipMode: false,
          excludeProjectId: mode === 'edit' ? projectId : undefined,
        }),
      })

      if (response.ok) {
        const result: ConflictResult = await response.json()
        setConflict(result.hasConflict ? result : null)
      }
    } catch (error) {
      console.error('Failed to check conflict:', error)
    } finally {
      setIsCheckingConflict(false)
    }
  }, [formData.targetDomain, formData.subdomainList, formData.ipMode, mode, projectId])

  // Debounced conflict check when form data changes
  useEffect(() => {
    const timer = setTimeout(() => {
      checkConflict()
    }, 500)

    return () => clearTimeout(timer)
  }, [checkConflict])

  // Fetch defaults from backend on mount (only for create mode)
  useEffect(() => {
    if (mode === 'create') {
      fetchDefaults().then(defaults => {
        setFormData(prev => ({ ...defaults, ...prev, ...initialData } as ProjectFormData))
        setIsLoadingDefaults(false)
      })
    }
  }, [mode, initialData])

  const updateField = <K extends keyof ProjectFormData>(
    field: K,
    value: ProjectFormData[K]
  ) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const updateMultipleFields = (fields: Partial<ProjectFormData>) => {
    setFormData(prev => ({ ...prev, ...fields }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.name.trim()) {
      alert('Project name is required')
      return
    }

    if (!formData.ipMode && !formData.targetDomain.trim()) {
      alert('Target domain is required')
      return
    }

    // Run field validation
    const validationErrors = validateProjectForm(formData as unknown as Record<string, unknown>)
    if (validationErrors.length > 0) {
      alert('Validation errors:\n' + validationErrors.map(e => `- ${e.message}`).join('\n'))
      return
    }

    // Block submission if there's a conflict
    if (conflict?.hasConflict) {
      alert('Cannot save project: ' + conflict.message)
      return
    }

    try {
      // Attach roeFile to form data for multipart submission
      const submitData = roeFile ? { ...formData, roeFile } : formData
      await onSubmit(submitData)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save project'
      if (message.toLowerCase().includes('guardrail')) {
        // Extract the reason after "Target blocked by guardrail: "
        const reason = message.replace(/^Target blocked by guardrail:\s*/i, '')
        setGuardrailError(reason || message)
      } else {
        alert(message)
      }
    }
  }

  // Determine if form can be submitted
  const canSubmit = !isSubmitting && !isLoadingDefaults && !conflict?.hasConflict && !isCheckingConflict

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.header}>
        <h1 className={styles.title}>
          {mode === 'create' ? 'Create New Project' : 'Project Settings'}
        </h1>
        <div className={styles.actions}>
          <button
            type="button"
            className="secondaryButton"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            <X size={14} />
            Cancel
          </button>
          {mode === 'edit' && projectId && (
            <button
              type="button"
              className="secondaryButton"
              onClick={() => window.open(`/api/projects/${projectId}/export`)}
            >
              <Download size={14} />
              Export
            </button>
          )}
          <button
            type="submit"
            className="primaryButton"
            disabled={!canSubmit}
          >
            {isLoadingDefaults ? (
              <>
                <Loader2 size={14} className={styles.spinner} />
                Loading...
              </>
            ) : isCheckingConflict ? (
              <>
                <Loader2 size={14} className={styles.spinner} />
                Checking...
              </>
            ) : (
              <>
                <Save size={14} />
                {isSubmitting ? 'Saving...' : 'Save Project'}
              </>
            )}
          </button>
        </div>
      </div>

      {/* Domain conflict warning banner */}
      {conflict?.hasConflict && (
        <div className={styles.conflictBanner}>
          <AlertTriangle size={20} className={styles.conflictIcon} />
          <div className={styles.conflictContent}>
            <div className={styles.conflictTitle}>Domain Conflict Detected</div>
            <div className={styles.conflictMessage}>{conflict.message}</div>
            {conflict.conflictingProject && (
              <div className={styles.conflictProject}>
                Conflicting project: <strong>{conflict.conflictingProject.name}</strong>
                {conflict.overlappingSubdomains.length > 0 && (
                  <> (subdomains: {conflict.overlappingSubdomains.join(', ')})</>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {isLoadingDefaults ? (
        <div className={styles.loadingContainer}>
          <Loader2 size={24} className={styles.spinner} />
          <p>Loading configuration defaults...</p>
        </div>
      ) : (
        <>
          <div className={styles.tabs}>
            {TAB_GROUPS.map((group, gi) => (
              <div key={gi} className={group.style ? styles[group.style] : styles.tabGroup}>
                {group.label && (
                  <span className={styles.tabGroupLabel}>{group.label}</span>
                )}
                <div className={styles.tabGroupTabs}>
                  {group.tabs.map(tab => (
                    <button
                      key={tab.id}
                      type="button"
                      className={`tab ${activeTab === tab.id ? 'tabActive' : ''} ${styles.compactTab} ${'wide' in tab && tab.wide ? styles.wideTab : ''}`}
                      onClick={() => setActiveTab(tab.id)}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className={styles.content}>
            {activeTab === 'roe' && (
          <RoeSection
            data={formData}
            updateField={updateField}
            updateMultipleFields={updateMultipleFields}
            mode={mode}
            onFileSelected={setRoeFile}
          />
        )}

        {activeTab === 'target' && (
          <>
            <TargetSection data={formData} updateField={updateField} mode={mode} />
            <ScanModulesSection data={formData} updateField={updateField} />
          </>
        )}

        {activeTab === 'discovery' && (
          <>
            <SubdomainDiscoverySection data={formData} updateField={updateField} />
            <ShodanSection data={formData} updateField={updateField} />
            <UrlscanSection data={formData} updateField={updateField} />
          </>
        )}

        {activeTab === 'port' && (
          <NaabuSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'http' && (
          <HttpxSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'resource' && (
          <>
            <KatanaSection data={formData} updateField={updateField} />
            <GauSection data={formData} updateField={updateField} />
            <KiterunnerSection data={formData} updateField={updateField} />
          </>
        )}

        {activeTab === 'vuln' && (
          <NucleiSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'cve' && (
          <>
            <CveLookupSection data={formData} updateField={updateField} />
            <MitreSection data={formData} updateField={updateField} />
          </>
        )}

        {activeTab === 'security' && (
          <SecurityChecksSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'integrations' && (
          <GithubSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'gvm' && (
          <GvmScanSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'agent' && (
          <AgentBehaviourSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'toolmatrix' && (
          <ToolMatrixSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'attack' && (
          <AttackSkillsSection data={formData} updateField={updateField} />
        )}

        {activeTab === 'cypherfix' && (
          <CypherFixSettingsSection data={formData} updateField={updateField} />
        )}
          </div>
        </>
      )}

      {/* Guardrail block modal */}
      {guardrailError && (
        <div className={styles.guardrailOverlay} onClick={() => setGuardrailError(null)}>
          <div className={styles.guardrailModal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.guardrailIconWrapper}>
              <ShieldAlert size={32} />
            </div>
            <h2 className={styles.guardrailTitle}>Target Blocked</h2>
            <p className={styles.guardrailMessage}>{guardrailError}</p>
            <p className={styles.guardrailHint}>
              This target appears to be a well-known public service that you are unlikely authorized to test.
              Please use a domain or IP range you own or have explicit permission to scan.
            </p>
            <button
              type="button"
              className={styles.guardrailButton}
              onClick={() => setGuardrailError(null)}
            >
              Understood
            </button>
          </div>
        </div>
      )}
    </form>
  )
}

export default ProjectForm
