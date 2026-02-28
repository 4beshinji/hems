import { useQuery } from '@tanstack/react-query'
import PCMetricsPanel from '@/components/digital/PCMetricsPanel'
import ServiceStatusPanel from '@/components/digital/ServiceStatusPanel'
import KnowledgePanel from '@/components/digital/KnowledgePanel'
import GASPanel from '@/components/digital/GASPanel'
import { fetchPC, fetchServices, fetchKnowledge, fetchGAS } from '@/lib/api'

export default function DigitalPage() {
  const pcQuery = useQuery({ queryKey: ['pc'], queryFn: fetchPC, refetchInterval: 10000 })
  const servicesQuery = useQuery({ queryKey: ['services'], queryFn: fetchServices, refetchInterval: 10000 })
  const knowledgeQuery = useQuery({ queryKey: ['knowledge'], queryFn: fetchKnowledge, refetchInterval: 10000 })
  const gasQuery = useQuery({ queryKey: ['gas'], queryFn: fetchGAS, refetchInterval: 10000 })

  return (
    <div className="space-y-4">
      <PCMetricsPanel pc={pcQuery.data ?? null} />
      <div className="grid gap-4 md:grid-cols-2">
        <ServiceStatusPanel services={servicesQuery.data ?? null} />
        <KnowledgePanel knowledge={knowledgeQuery.data ?? null} />
      </div>
      <GASPanel gas={gasQuery.data ?? null} />
    </div>
  )
}
