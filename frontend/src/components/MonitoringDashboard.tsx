import { useEffect, useState, useCallback } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Button, Typography, Space, message } from 'antd';
import {
  CloudServerOutlined,
  PhoneOutlined,
  ClockCircleOutlined,
  EyeOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { getEcsStatus, getActiveCallsSummary, listCallRecords } from '../api';
import { LiveTranscriptViewer } from './LiveTranscriptViewer';
import type { EcsStatus, ActiveCall, DynamoCallRecord } from '../types';

const { Title } = Typography;

export function MonitoringDashboard() {
  const [ecsStatus, setEcsStatus] = useState<EcsStatus | null>(null);
  const [activeCalls, setActiveCalls] = useState<ActiveCall[]>([]);
  const [callRecords, setCallRecords] = useState<DynamoCallRecord[]>([]);
  const [loading, setLoading] = useState({ ecs: false, active: false, records: false });
  const [selectedCallSid, setSelectedCallSid] = useState<string | null>(null);
  const [selectedMeta, setSelectedMeta] = useState<{ name?: string; phone?: string }>({});

  const fetchEcs = useCallback(async () => {
    try {
      setLoading((l) => ({ ...l, ecs: true }));
      const data = await getEcsStatus();
      setEcsStatus(data);
    } catch {
      // silent
    } finally {
      setLoading((l) => ({ ...l, ecs: false }));
    }
  }, []);

  const fetchActive = useCallback(async () => {
    try {
      setLoading((l) => ({ ...l, active: true }));
      const data = await getActiveCallsSummary();
      setActiveCalls(data.activeCalls);
    } catch {
      // silent
    } finally {
      setLoading((l) => ({ ...l, active: false }));
    }
  }, []);

  const fetchRecords = useCallback(async () => {
    try {
      setLoading((l) => ({ ...l, records: true }));
      const data = await listCallRecords({ limit: 50, days: 7 });
      setCallRecords(data.records);
    } catch {
      // silent
    } finally {
      setLoading((l) => ({ ...l, records: false }));
    }
  }, []);

  // Initial fetch + polling
  useEffect(() => {
    fetchEcs();
    fetchActive();
    fetchRecords();

    const ecsInterval = setInterval(fetchEcs, 15000);
    const activeInterval = setInterval(fetchActive, 3000);
    const recordsInterval = setInterval(fetchRecords, 10000);

    return () => {
      clearInterval(ecsInterval);
      clearInterval(activeInterval);
      clearInterval(recordsInterval);
    };
  }, [fetchEcs, fetchActive, fetchRecords]);

  const formatDuration = (startTime: string, endTime?: string) => {
    const start = new Date(startTime).getTime();
    const end = endTime ? new Date(endTime).getTime() : Date.now();
    const diff = Math.floor((end - start) / 1000);
    const m = Math.floor(diff / 60);
    const s = diff % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const handleViewLive = (call: ActiveCall) => {
    setSelectedCallSid(call.callSid);
    setSelectedMeta({ name: call.customerName, phone: call.customerPhone });
  };

  const handleViewRecord = (record: DynamoCallRecord) => {
    setSelectedCallSid(record.callSid);
    setSelectedMeta({ name: record.customerName, phone: record.customerPhone });
  };

  const avgDuration = () => {
    const completed = callRecords.filter((r) => r.status === 'completed' && r.startTime && r.endTime);
    if (completed.length === 0) return '--';
    const totalMs = completed.reduce((sum, r) => {
      return sum + (new Date(r.endTime!).getTime() - new Date(r.startTime).getTime());
    }, 0);
    const avgSec = Math.floor(totalMs / completed.length / 1000);
    const m = Math.floor(avgSec / 60);
    const s = avgSec % 60;
    return `${m}m ${s}s`;
  };

  const activeColumns = [
    {
      title: 'Phone',
      dataIndex: 'customerPhone',
      key: 'phone',
      width: 140,
      render: (v: string) => v || '-',
    },
    {
      title: 'Name',
      dataIndex: 'customerName',
      key: 'name',
      width: 120,
      render: (v: string) => v || '-',
    },
    {
      title: 'Duration',
      key: 'duration',
      width: 90,
      render: (_: unknown, r: ActiveCall) => formatDuration(r.startTime),
    },
    {
      title: 'Turns',
      dataIndex: 'turnCount',
      key: 'turns',
      width: 70,
    },
    {
      title: 'Action',
      key: 'action',
      width: 80,
      render: (_: unknown, r: ActiveCall) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewLive(r)}>
          View
        </Button>
      ),
    },
  ];

  const recordColumns = [
    {
      title: 'Time',
      dataIndex: 'startTime',
      key: 'time',
      width: 90,
      render: (v: string) => {
        try {
          return new Date(v).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
        } catch {
          return v;
        }
      },
    },
    {
      title: 'Phone',
      dataIndex: 'customerPhone',
      key: 'phone',
      width: 140,
      render: (v: string) => v || '-',
    },
    {
      title: 'Name',
      dataIndex: 'customerName',
      key: 'name',
      width: 120,
      render: (v: string) => v || '-',
    },
    {
      title: 'Duration',
      key: 'duration',
      width: 90,
      render: (_: unknown, r: DynamoCallRecord) =>
        r.endTime ? formatDuration(r.startTime, r.endTime) : '--',
    },
    {
      title: 'Turns',
      key: 'turns',
      width: 70,
      render: (_: unknown, r: DynamoCallRecord) => r.turnCount ?? r.transcriptCount ?? 0,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => {
        const color = v === 'active' ? 'green' : v === 'completed' ? 'default' : 'red';
        return <Tag color={color}>{v === 'completed' ? 'Done' : v}</Tag>;
      },
    },
    {
      title: 'Action',
      key: 'action',
      width: 80,
      render: (_: unknown, r: DynamoCallRecord) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewRecord(r)}>
          View
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={4} style={{ margin: 0 }}>Monitoring Dashboard</Title>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => {
            fetchEcs();
            fetchActive();
            fetchRecords();
            message.success('Refreshed');
          }}
        >
          Refresh
        </Button>
      </Space>

      {/* Stats cards */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="ECS Instances"
              value={ecsStatus ? `${ecsStatus.runningCount} / ${ecsStatus.desiredCount}` : '--'}
              prefix={<CloudServerOutlined />}
              loading={loading.ecs}
              valueStyle={{ color: ecsStatus && ecsStatus.runningCount >= ecsStatus.desiredCount ? '#3f8600' : '#cf1322' }}
            />
            {ecsStatus && ecsStatus.pendingCount > 0 && (
              <Tag color="orange" style={{ marginTop: 4 }}>{ecsStatus.pendingCount} pending</Tag>
            )}
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="Active Calls"
              value={activeCalls.length}
              prefix={<PhoneOutlined />}
              loading={loading.active}
              valueStyle={{ color: activeCalls.length > 0 ? '#1677ff' : undefined }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="Avg Duration (today)"
              value={avgDuration()}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Active calls table */}
      <Card
        title={`Active Calls (auto-refresh 3s)`}
        size="small"
        style={{ marginBottom: 24 }}
      >
        <Table
          dataSource={activeCalls}
          columns={activeColumns}
          rowKey="callSid"
          size="small"
          pagination={false}
          loading={loading.active}
          locale={{ emptyText: 'No active calls' }}
        />
      </Card>

      {/* Recent call records */}
      <Card title="Recent Call Records (auto-refresh 10s)" size="small">
        <Table
          dataSource={callRecords}
          columns={recordColumns}
          rowKey="callSid"
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: false }}
          loading={loading.records}
          locale={{ emptyText: 'No call records' }}
        />
      </Card>

      {/* Live transcript viewer drawer */}
      <LiveTranscriptViewer
        callSid={selectedCallSid}
        customerName={selectedMeta.name}
        customerPhone={selectedMeta.phone}
        onClose={() => setSelectedCallSid(null)}
      />
    </div>
  );
}
