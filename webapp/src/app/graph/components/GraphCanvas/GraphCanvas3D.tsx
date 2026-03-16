'use client'

import { useRef, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { GraphData, GraphNode, GraphLink } from '../../types'
import { getNodeColor, getNodeSize, getGlowLevel } from '../../utils'
import { getLinkColor, getLinkWidth3D, getParticleCount, getParticleWidth, getParticleColor, getParticleSpeed } from '../../utils/linkHelpers'
import {
  LINK_SIZES,
  BASE_SIZES,
  BACKGROUND_COLORS,
  SELECTION_COLORS,
  CHAIN_SESSION_COLORS,
  GOAL_FINDING_COLORS,
  ANIMATION_CONFIG,
  THREE_CONFIG,
} from '../../config'
import { hasHighSeverityNodes, isGoalFinding } from '../../utils/nodeHelpers'
import { useAnimationFrame } from '../../hooks'

const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), {
  ssr: false,
})

interface GraphCanvas3DProps {
  data: GraphData
  width: number
  height: number
  showLabels: boolean
  selectedNode: GraphNode | null
  onNodeClick: (node: GraphNode) => void
  isDark?: boolean
  activeChainId?: string
}

export function GraphCanvas3D({
  data,
  width,
  height,
  showLabels,
  selectedNode,
  onNodeClick,
  isDark = true,
  activeChainId,
}: GraphCanvas3DProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graph3DRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const glowRingsRef = useRef<any[]>([])

  // Clear glow rings when data changes
  useEffect(() => {
    glowRingsRef.current = []
  }, [data])

  // Animation loop for pulsing glow rings
  const hasHighSeverity = hasHighSeverityNodes(data.nodes)

  useAnimationFrame(
    (time) => {
      glowRingsRef.current.forEach((ring) => {
        if (ring) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const glowLevel = (ring as any).__glowLevel || 'high'
          const speed = glowLevel === 'critical' ? ANIMATION_CONFIG.criticalSpeed : ANIMATION_CONFIG.highSpeed
          const pulse = Math.sin(time * speed) * 0.15 + 1
          const opacity = Math.sin(time * speed) * 0.2 + 0.4

          ring.scale.set(pulse, pulse, 1)
          if (ring.material) {
            ring.material.opacity = opacity
          }
        }
      })
    },
    hasHighSeverity
  )

  const selectedNodeId = selectedNode?.id

  return (
    <ForceGraph3D
      ref={graph3DRef}
      graphData={data}
      nodeLabel={(node) => `${(node as GraphNode).name} (${(node as GraphNode).type})`}
      nodeColor={(node) => getNodeColor(node as GraphNode)}
      nodeRelSize={BASE_SIZES.node3D}
      nodeOpacity={THREE_CONFIG.nodeOpacity}
      linkLabel={(link) => (link as GraphLink).type}
      linkColor={(link) => getLinkColor(link as GraphLink, selectedNodeId)}
      linkWidth={(link) => getLinkWidth3D(link as GraphLink, selectedNodeId)}
      linkDirectionalParticles={(link) => getParticleCount(link as GraphLink, selectedNodeId)}
      linkDirectionalParticleWidth={(link) => getParticleWidth(link as GraphLink, selectedNodeId)}
      linkDirectionalParticleColor={(link) => getParticleColor(link as GraphLink, activeChainId)}
      linkDirectionalParticleSpeed={(link) => getParticleSpeed(link as GraphLink)}
      linkDirectionalArrowLength={LINK_SIZES.arrowLength3D}
      linkDirectionalArrowRelPos={1}
      backgroundColor={isDark ? BACKGROUND_COLORS.dark.graph : BACKGROUND_COLORS.light.graph}
      width={width}
      height={height}
      onNodeClick={(node) => onNodeClick(node as GraphNode)}
      nodeThreeObject={(node: object) => {
        const graphNode = node as GraphNode
        const THREE = require('three')
        const SpriteText = require('three-spritetext').default

        const group = new THREE.Group()

        const sphereSize = BASE_SIZES.node3D * getNodeSize(graphNode)
        const nodeColor = getNodeColor(graphNode)
        const isSelected = selectedNodeId === graphNode.id

        // Add selection marker ring (green) for selected node
        if (isSelected) {
          const selectGeometry = new THREE.RingGeometry(
            sphereSize * THREE_CONFIG.selectionRingScale.inner,
            sphereSize * THREE_CONFIG.selectionRingScale.outer,
            THREE_CONFIG.ringSegments
          )
          const selectMaterial = new THREE.MeshBasicMaterial({
            color: SELECTION_COLORS.ring,
            transparent: true,
            opacity: THREE_CONFIG.selectionRingOpacity,
            side: THREE.DoubleSide,
          })
          const selectRing = new THREE.Mesh(selectGeometry, selectMaterial)
          selectRing.lookAt(0, 0, 1)
          group.add(selectRing)
        }

        // Determine chain membership and effective color
        const isExploit = graphNode.type === 'ExploitGvm' || graphNode.type === 'ChainFinding'
        const isChainNode = graphNode.type === 'AttackChain' || graphNode.type === 'ChainStep' || graphNode.type === 'ChainDecision' || graphNode.type === 'ChainFailure'
        const isInActiveChain = isChainNode && !!activeChainId && graphNode.properties?.chain_id === activeChainId
        const isExploitInActiveChain = isExploit && !!activeChainId && graphNode.properties?.chain_id === activeChainId
        const isActiveChain = graphNode.type === 'AttackChain' && isInActiveChain
        const isGoal = isGoalFinding(graphNode)
        // Inactive chain nodes: grey (dark yellow for diamonds, dark green for goal findings)
        let effectiveColor: string
        if ((isChainNode || isExploit) && !isInActiveChain && !isExploitInActiveChain) {
          if (isGoal) {
            effectiveColor = isSelected ? GOAL_FINDING_COLORS.active : GOAL_FINDING_COLORS.inactive
          } else if (isExploit) {
            effectiveColor = isSelected ? CHAIN_SESSION_COLORS.inactiveSelected : CHAIN_SESSION_COLORS.inactiveFinding
          } else {
            effectiveColor = isSelected ? CHAIN_SESSION_COLORS.inactiveSelected : CHAIN_SESSION_COLORS.inactive
          }
        } else {
          effectiveColor = nodeColor
        }

        // Add active-session marker ring (yellow, dashed) on matching AttackChain
        if (isActiveChain) {
          const activeGeometry = new THREE.RingGeometry(
            sphereSize * 1.8,
            sphereSize * 2.0,
            6 // hexagonal ring
          )
          const activeMaterial = new THREE.MeshBasicMaterial({
            color: CHAIN_SESSION_COLORS.activeRing, // yellow
            transparent: true,
            opacity: 0.7,
            side: THREE.DoubleSide,
          })
          const activeRing = new THREE.Mesh(activeGeometry, activeMaterial)
          activeRing.lookAt(0, 0, 1)
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ;(activeRing as any).__isActiveChainRing = true
          ;(activeRing as any).__glowLevel = 'high'
          glowRingsRef.current.push(activeRing)
          group.add(activeRing)
        }

        // Add outer glow ring for high/critical severity
        const glowLevel = getGlowLevel(graphNode)
        const glowColor = (isChainNode || isExploit) ? effectiveColor : nodeColor
        if (glowLevel) {
          const glowGeometry = new THREE.RingGeometry(
            sphereSize * THREE_CONFIG.glowRingScale.inner,
            sphereSize * THREE_CONFIG.glowRingScale.outer,
            THREE_CONFIG.ringSegments
          )
          const glowMaterial = new THREE.MeshBasicMaterial({
            color: glowColor,
            transparent: true,
            opacity: THREE_CONFIG.glowRingOpacity,
            side: THREE.DoubleSide,
          })
          const glowRing = new THREE.Mesh(glowGeometry, glowMaterial)

          glowRing.lookAt(0, 0, 1)

          // Store reference for animation with glow level
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ;(glowRing as any).__glowLevel = glowLevel
          glowRingsRef.current.push(glowRing)

          group.add(glowRing)
        }

        // Choose geometry based on node type
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let geometry: any
        if (isExploit) {
          geometry = new THREE.OctahedronGeometry(sphereSize * 1.2)
        } else if (isChainNode) {
          geometry = new THREE.DodecahedronGeometry(sphereSize * 1.1)
        } else {
          geometry = new THREE.SphereGeometry(sphereSize, THREE_CONFIG.sphereSegments, THREE_CONFIG.sphereSegments)
        }

        const isSpecialNode = isExploit || isChainNode
        const material = isSpecialNode
          ? new THREE.MeshLambertMaterial({
              color: effectiveColor,
              transparent: true,
              opacity: 0.12,
              emissive: effectiveColor,
              emissiveIntensity: 0.3,
              side: THREE.DoubleSide,
            })
          : new THREE.MeshLambertMaterial({
              color: nodeColor,
              transparent: true,
              opacity: THREE_CONFIG.nodeOpacity,
            })
        const mesh = new THREE.Mesh(geometry, material)
        group.add(mesh)

        // Add wireframe overlay for exploit nodes
        if (isExploit) {
          const wireMaterial = new THREE.MeshBasicMaterial({
            color: effectiveColor,
            wireframe: true,
            transparent: true,
            opacity: 0.6,
          })
          const wireMesh = new THREE.Mesh(geometry, wireMaterial)
          group.add(wireMesh)
        }

        // Wireframe overlay for external domain nodes (dashed appearance in 3D)
        if (graphNode.type === 'ExternalDomain') {
          const wireMaterial = new THREE.MeshBasicMaterial({
            color: nodeColor,
            wireframe: true,
            transparent: true,
            opacity: 0.5,
          })
          const wireMesh = new THREE.Mesh(geometry, wireMaterial)
          group.add(wireMesh)
        }

        // Add clean edge outline for chain nodes (only polygon edges, no triangulation)
        if (isChainNode) {
          const edges = new THREE.EdgesGeometry(geometry, 15)
          const lineMaterial = new THREE.LineBasicMaterial({
            color: effectiveColor,
            transparent: true,
            opacity: 0.7,
          })
          const lineSegments = new THREE.LineSegments(edges, lineMaterial)
          group.add(lineSegments)
        }

        // Create label if enabled or if node is selected
        if (showLabels || isSelected) {
          const sprite = new SpriteText(graphNode.name)
          sprite.color = isDark ? BACKGROUND_COLORS.dark.label : BACKGROUND_COLORS.light.label
          sprite.textHeight = BASE_SIZES.label3D
          sprite.position.y = sphereSize + BASE_SIZES.label3D
          group.add(sprite)
        }

        return group
      }}
    />
  )
}
