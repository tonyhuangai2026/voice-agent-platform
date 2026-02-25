import { useState, useEffect } from 'react';
import { Card, Table, Button, Select, Space, Typography, Tag, message, Tooltip } from 'antd';
import { ReloadOutlined, PhoneOutlined, MessageOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listContacts } from '../api';
import type { Contact } from '../types';

const { Title, Text } = Typography;

interface ContactListProps {
  onSelectContact: (contactId: string) => void;
}

export function ContactList({ onSelectContact }: ContactListProps) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(false);
  const [channel, setChannel] = useState<string>('VOICE');
  const [days, setDays] = useState<number>(7);

  const fetchContacts = async () => {
    setLoading(true);
    try {
      const data = await listContacts(100, channel, days);
      setContacts(data.contacts);
    } catch (error) {
      console.error('Failed to fetch contacts:', error);
      message.error('Failed to load contacts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContacts();
  }, [channel, days]);

  const getDisconnectReasonTag = (reason: string | undefined) => {
    if (!reason) return null;
    const colorMap: Record<string, string> = {
      'CUSTOMER_DISCONNECT': 'green',
      'AGENT_DISCONNECT': 'blue',
      'TELECOM_PROBLEM': 'red',
      'EXPIRED': 'orange',
      'CONTACT_FLOW_DISCONNECT': 'purple',
    };
    return <Tag color={colorMap[reason] || 'default'}>{reason}</Tag>;
  };

  const columns: ColumnsType<Contact> = [
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
      title: 'Debt Amount',
      dataIndex: 'debtAmount',
      key: 'debtAmount',
      render: (amount: string) => (
        amount ? <Tag color="red">${amount}</Tag> : <Text type="secondary">-</Text>
      ),
    },
    {
      title: 'Time',
      dataIndex: 'initiationTimestamp',
      key: 'initiationTimestamp',
      render: (timestamp: string) => (
        <Tooltip title={timestamp}>
          <Text>{dayjs(timestamp).format('MM-DD HH:mm')}</Text>
        </Tooltip>
      ),
      sorter: (a, b) => new Date(a.initiationTimestamp).getTime() - new Date(b.initiationTimestamp).getTime(),
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
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Button
          type="link"
          icon={<MessageOutlined />}
          onClick={() => onSelectContact(record.contactId)}
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
            Contact List
          </Title>
          <Space>
            <Select
              value={channel}
              onChange={setChannel}
              style={{ width: 120 }}
              options={[
                { value: 'VOICE', label: 'Voice Calls' },
                { value: 'CHAT', label: 'Chat' },
              ]}
            />
            <Select
              value={days}
              onChange={setDays}
              style={{ width: 120 }}
              options={[
                { value: 1, label: 'Last 1 day' },
                { value: 3, label: 'Last 3 days' },
                { value: 7, label: 'Last 7 days' },
                { value: 14, label: 'Last 14 days' },
              ]}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchContacts}
              loading={loading}
            >
              Refresh
            </Button>
          </Space>
        </div>

        <Table
          columns={columns}
          dataSource={contacts}
          rowKey="contactId"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} contacts`,
          }}
          size="small"
        />
      </Space>
    </Card>
  );
}
