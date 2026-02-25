import { useState, useEffect } from 'react';
import { Card, Table, Button, Space, Typography, Tag, message, Tooltip, Select } from 'antd';
import { ReloadOutlined, MessageOutlined, PhoneOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { listTranscripts } from '../api';
import type { Transcript } from '../types';

const { Title, Text } = Typography;

interface TranscriptListProps {
  onSelectTranscript: (contactId: string) => void;
}

export function TranscriptList({ onSelectTranscript }: TranscriptListProps) {
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(7);

  const fetchTranscripts = async () => {
    setLoading(true);
    try {
      const data = await listTranscripts(100, days);
      setTranscripts(data.transcripts);
    } catch (error) {
      console.error('Failed to fetch transcripts:', error);
      message.error('Failed to load transcripts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTranscripts();
  }, [days]);

  const columns: ColumnsType<Transcript> = [
    {
      title: 'Customer',
      key: 'customer',
      render: (_, record: any) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.customerName || 'Unknown'}</Text>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            <PhoneOutlined /> {record.customerPhone || 'N/A'}
          </Text>
        </Space>
      ),
    },
    {
      title: 'System Phone',
      key: 'systemPhone',
      render: (_: any, record: any) => (
        <Text code style={{ fontSize: '12px' }}>
          {record.systemPhone || 'N/A'}
        </Text>
      ),
    },
    {
      title: 'Debt',
      key: 'debtAmount',
      render: (_: any, record: any) => (
        record.debtAmount ? <Tag color="red">${record.debtAmount}</Tag> : <Text type="secondary">-</Text>
      ),
    },
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (timestamp: string) => {
        const parsed = timestamp.replace('T', ' ');
        return (
          <Tooltip title={timestamp}>
            <Text>{parsed}</Text>
          </Tooltip>
        );
      },
      sorter: (a, b) => a.timestamp.localeCompare(b.timestamp),
      defaultSortOrder: 'descend',
    },
    {
      title: 'Result',
      key: 'disconnectReason',
      render: (_: any, record: any) => {
        if (!record.disconnectReason) return null;
        const colorMap: Record<string, string> = {
          'CUSTOMER_DISCONNECT': 'green',
          'AGENT_DISCONNECT': 'blue',
          'TELECOM_PROBLEM': 'red',
          'EXPIRED': 'orange',
        };
        return <Tag color={colorMap[record.disconnectReason] || 'default'}>{record.disconnectReason}</Tag>;
      },
    },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Button
          type="link"
          icon={<MessageOutlined />}
          onClick={() => onSelectTranscript(record.contactId)}
        >
          View Chat
        </Button>
      ),
    },
  ];

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            <MessageOutlined style={{ marginRight: 8 }} />
            Chat Records
          </Title>
          <Space>
            <Select
              value={days}
              onChange={setDays}
              style={{ width: 140 }}
              options={[
                { value: 1, label: 'Last 1 day' },
                { value: 3, label: 'Last 3 days' },
                { value: 7, label: 'Last 7 days' },
                { value: 14, label: 'Last 14 days' },
                { value: 30, label: 'Last 30 days' },
              ]}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchTranscripts}
              loading={loading}
            >
              Refresh
            </Button>
          </Space>
        </div>

        <Table
          columns={columns}
          dataSource={transcripts}
          rowKey="contactId"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} records`,
          }}
          size="small"
        />
      </Space>
    </Card>
  );
}
