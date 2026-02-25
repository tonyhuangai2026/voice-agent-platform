import { useState, useEffect } from 'react';
import { Card, Table, Button, Select, Space, Typography, Tag, message, Tooltip, Progress } from 'antd';
import { ReloadOutlined, PhoneOutlined, MessageOutlined, AudioOutlined, DownloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listAllRecords, getTranscript } from '../api';
import type { CallRecord } from '../types';

const { Title, Text } = Typography;

interface AllRecordsListProps {
  onSelectRecord: (contactId: string) => void;
}

export function AllRecordsList({ onSelectRecord }: AllRecordsListProps) {
  const [records, setRecords] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [days, setDays] = useState<number>(7);

  const fetchRecords = async () => {
    setLoading(true);
    try {
      const data = await listAllRecords(200, days);
      setRecords(data.records);
    } catch (error) {
      console.error('Failed to fetch records:', error);
      message.error('Failed to load records');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    setExportProgress(0);
    try {
      // Fetch records with higher limit for export
      const data = await listAllRecords(200, days);
      const allRecords = data.records;
      setExportProgress(10);

      // Fetch transcripts for records that have them
      const withTranscript = allRecords.filter(r => r.hasTranscript);
      const transcriptMap: Record<string, string> = {};
      const batchSize = 5;

      for (let i = 0; i < withTranscript.length; i += batchSize) {
        const batch = withTranscript.slice(i, i + batchSize);
        const results = await Promise.allSettled(
          batch.map(r => getTranscript(r.contactId))
        );
        results.forEach((result, idx) => {
          if (result.status === 'fulfilled' && result.value.messages?.length) {
            const msgs = result.value.messages
              .map(m => `[${m.role}] ${m.content}`)
              .join(' | ');
            transcriptMap[batch[idx].contactId] = msgs;
          }
        });
        setExportProgress(10 + Math.round((i + batchSize) / withTranscript.length * 80));
      }

      // Build CSV
      const csvHeader = 'Contact ID,Customer Name,Phone,Debt,Channel,Method,Time,Disconnect Reason,Has Transcript,Conversation\n';
      const csvRows = allRecords.map(r => {
        const conversation = (transcriptMap[r.contactId] || '').replace(/"/g, '""');
        return [
          r.contactId,
          `"${(r.customerName || '').replace(/"/g, '""')}"`,
          r.customerPhone || '',
          r.debtAmount || '',
          r.channel || '',
          r.initiationMethod || '',
          r.timestamp || '',
          r.disconnectReason || '',
          r.hasTranscript ? 'Yes' : 'No',
          `"${conversation}"`,
        ].join(',');
      }).join('\n');

      // Download
      const BOM = '\uFEFF';
      const blob = new Blob([BOM + csvHeader + csvRows], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `call_records_${dayjs().format('YYYY-MM-DD_HHmm')}.csv`;
      a.click();
      URL.revokeObjectURL(url);

      setExportProgress(100);
      message.success(`Exported ${allRecords.length} records (${Object.keys(transcriptMap).length} with transcripts)`);
    } catch (error) {
      console.error('Export failed:', error);
      message.error('Export failed');
    } finally {
      setExporting(false);
      setExportProgress(0);
    }
  };

  useEffect(() => {
    fetchRecords();
  }, [days]);

  const getDisconnectReasonTag = (reason: string | undefined) => {
    if (!reason) return <Text type="secondary">-</Text>;
    const colorMap: Record<string, string> = {
      'CUSTOMER_DISCONNECT': 'green',
      'AGENT_DISCONNECT': 'blue',
      'TELECOM_PROBLEM': 'red',
      'EXPIRED': 'orange',
      'CONTACT_FLOW_DISCONNECT': 'purple',
    };
    return <Tag color={colorMap[reason] || 'default'}>{reason}</Tag>;
  };

  const columns: ColumnsType<CallRecord> = [
    {
      title: 'Type',
      dataIndex: 'channel',
      key: 'channel',
      width: 80,
      render: (channel: string) => (
        <Tag color={channel === 'VOICE' ? 'blue' : 'green'} icon={channel === 'VOICE' ? <AudioOutlined /> : <MessageOutlined />}>
          {channel}
        </Tag>
      ),
      filters: [
        { text: 'Voice', value: 'VOICE' },
        { text: 'Chat', value: 'CHAT' },
      ],
      onFilter: (value, record) => record.channel === value,
    },
    {
      title: 'Customer',
      key: 'customer',
      render: (_, record) => (
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
      dataIndex: 'systemPhone',
      key: 'systemPhone',
      render: (phone: string) => (
        <Text code style={{ fontSize: '12px' }}>
          {phone || 'N/A'}
        </Text>
      ),
    },
    {
      title: 'Debt',
      dataIndex: 'debtAmount',
      key: 'debtAmount',
      render: (amount: string) => (
        amount ? <Tag color="red">${amount}</Tag> : <Text type="secondary">-</Text>
      ),
    },
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (timestamp: string) => (
        <Tooltip title={timestamp}>
          <Text>{dayjs(timestamp).format('MM-DD HH:mm')}</Text>
        </Tooltip>
      ),
      sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: 'Method',
      dataIndex: 'initiationMethod',
      key: 'initiationMethod',
      render: (method: string) => (
        <Tag color={method === 'API' ? 'blue' : 'green'}>{method}</Tag>
      ),
    },
    {
      title: 'Result',
      dataIndex: 'disconnectReason',
      key: 'disconnectReason',
      render: getDisconnectReasonTag,
    },
    {
      title: 'Chat',
      dataIndex: 'hasTranscript',
      key: 'hasTranscript',
      width: 60,
      render: (has: boolean) => (
        has ? <Tag color="cyan"><MessageOutlined /></Tag> : <Text type="secondary">-</Text>
      ),
    },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Button
          type="link"
          icon={<MessageOutlined />}
          onClick={() => onSelectRecord(record.contactId)}
        >
          Details
        </Button>
      ),
    },
  ];

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            <PhoneOutlined style={{ marginRight: 8 }} />
            All Records (Voice + Chat)
          </Title>
          <Space>
            <Select
              value={days}
              onChange={setDays}
              style={{ width: 120 }}
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
              onClick={fetchRecords}
              loading={loading}
            >
              Refresh
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExport}
              loading={exporting}
            >
              Export CSV
            </Button>
          </Space>
        </div>

        {exporting && (
          <Progress percent={exportProgress} size="small" status="active" />
        )}

        <Table
          columns={columns}
          dataSource={records}
          rowKey="contactId"
          loading={loading}
          pagination={{
            defaultPageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (total) => `Total ${total} records`,
          }}
          size="small"
        />
      </Space>
    </Card>
  );
}
