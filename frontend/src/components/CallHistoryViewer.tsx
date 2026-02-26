import { useState, useEffect } from 'react';
import { Card, Table, Input, Select, Space, Tag, Button, Modal, Typography, Descriptions, Empty, Spin, message, Popconfirm, Form, Radio, Checkbox } from 'antd';
import { SearchOutlined, MessageOutlined, PhoneOutlined, ClockCircleOutlined, UserOutlined, RobotOutlined, DeleteOutlined, TagsOutlined, ThunderboltOutlined, FileTextOutlined, DownloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import { listCallRecords, deleteCallRecord, listLabels, updateCallLabels, autoLabelCall, getCallRecordingUrl } from '../api';
import type { DynamoCallRecord, LabelConfig, CallLabels } from '../types';
import { useProject } from '../contexts/ProjectContext';
import LogViewer from './LogViewer';

dayjs.extend(duration);

const { Text, Title } = Typography;
const { Search } = Input;

interface TranscriptEntry {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

export function CallHistoryViewer() {
  const { currentProject } = useProject();
  const [callRecords, setCallRecords] = useState<DynamoCallRecord[]>([]);
  const [filteredRecords, setFilteredRecords] = useState<DynamoCallRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedCall, setSelectedCall] = useState<DynamoCallRecord | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [labelModalVisible, setLabelModalVisible] = useState(false);
  const [labelingCall, setLabelingCall] = useState<DynamoCallRecord | null>(null);
  const [labelConfigs, setLabelConfigs] = useState<LabelConfig[]>([]);
  const [autoLabeling, setAutoLabeling] = useState(false);
  const [labelForm] = Form.useForm();
  const [logViewerVisible, setLogViewerVisible] = useState(false);
  const [logViewerCallSid, setLogViewerCallSid] = useState<string>('');

  useEffect(() => {
    fetchCallRecords();
    fetchLabelConfigs();
  }, [currentProject]);

  useEffect(() => {
    filterRecords();
  }, [callRecords, searchText, statusFilter]);

  const fetchCallRecords = async () => {
    setLoading(true);
    try {
      const data = await listCallRecords(100, undefined);
      // Filter by project if selected
      let records = data.records;
      if (currentProject) {
        records = records.filter(r => r.project_id === currentProject.project_id);
      }
      setCallRecords(records);
    } catch (error) {
      message.error('Failed to load call records');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const filterRecords = () => {
    let filtered = [...callRecords];

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(r => r.status === statusFilter);
    }

    // Search filter (by customer name or phone)
    if (searchText) {
      const search = searchText.toLowerCase();
      filtered = filtered.filter(r =>
        r.customerName?.toLowerCase().includes(search) ||
        r.customerPhone?.toLowerCase().includes(search) ||
        r.callSid?.toLowerCase().includes(search)
      );
    }

    setFilteredRecords(filtered);
  };

  const handleViewTranscript = (record: DynamoCallRecord) => {
    setSelectedCall(record);
    setModalVisible(true);
  };

  const handleDelete = async (callSid: string) => {
    try {
      await deleteCallRecord(callSid);
      message.success('Call record deleted successfully');
      fetchCallRecords();
    } catch (error) {
      message.error('Failed to delete call record');
      console.error(error);
    }
  };

  const fetchLabelConfigs = async () => {
    if (!currentProject) return;
    try {
      const data = await listLabels(currentProject.project_id, true);
      setLabelConfigs(data.labels);
    } catch (error) {
      console.error('Failed to fetch label configs:', error);
    }
  };

  const handleOpenLabelModal = (record: DynamoCallRecord) => {
    setLabelingCall(record);
    // Populate form with existing labels
    const formValues: any = {};
    if (record.labels) {
      Object.keys(record.labels).forEach(labelId => {
        formValues[labelId] = record.labels![labelId];
      });
    }
    labelForm.setFieldsValue(formValues);
    setLabelModalVisible(true);
  };

  const handleSaveLabels = async () => {
    if (!labelingCall) return;
    try {
      const values = labelForm.getFieldsValue();
      // Filter out undefined values
      const labels: CallLabels = {};
      Object.keys(values).forEach(key => {
        if (values[key] !== undefined && values[key] !== null) {
          labels[key] = values[key];
        }
      });

      await updateCallLabels(labelingCall.callSid, labels);
      message.success('Labels updated successfully');
      setLabelModalVisible(false);
      fetchCallRecords();
    } catch (error) {
      message.error('Failed to update labels');
      console.error(error);
    }
  };

  const handleAutoLabel = async (callSid: string) => {
    setAutoLabeling(true);
    try {
      await autoLabelCall(callSid);
      message.success('Call automatically labeled by AI');
      fetchCallRecords();
    } catch (error: any) {
      message.error(error.response?.data?.error || 'Failed to auto-label call');
      console.error(error);
    } finally {
      setAutoLabeling(false);
    }
  };

  const handleDownloadRecording = async (callSid: string) => {
    try {
      const data = await getCallRecordingUrl(callSid);
      window.open(data.downloadUrl, '_blank');
    } catch (error: any) {
      message.error(error.response?.data?.error || 'Failed to download recording');
      console.error(error);
    }
  };

  const calculateDuration = (startTime?: string, endTime?: string) => {
    if (!startTime || !endTime) return '-';
    const start = dayjs(startTime);
    const end = dayjs(endTime);
    const diff = end.diff(start, 'second');
    const mins = Math.floor(diff / 60);
    const secs = diff % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const columns: ColumnsType<DynamoCallRecord> = [
    {
      title: 'Call SID',
      dataIndex: 'callSid',
      key: 'callSid',
      width: 150,
      render: (sid: string) => (
        <Text code style={{ fontSize: 11 }}>
          {sid.substring(0, 12)}...
        </Text>
      ),
    },
    {
      title: 'Customer',
      key: 'customer',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.customerName || 'Unknown'}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <PhoneOutlined /> {record.customerPhone || '-'}
          </Text>
        </Space>
      ),
    },
    {
      title: 'Voice',
      dataIndex: 'voiceId',
      key: 'voiceId',
      width: 100,
      render: (voice: string) => <Tag>{voice || 'default'}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const color = status === 'completed' ? 'green' : status === 'active' ? 'blue' : 'default';
        return <Tag color={color}>{status}</Tag>;
      },
    },
    {
      title: 'Start Time',
      dataIndex: 'startTime',
      key: 'startTime',
      width: 150,
      render: (time: string) => time ? dayjs(time).format('MM-DD HH:mm:ss') : '-',
      sorter: (a, b) => dayjs(a.startTime).unix() - dayjs(b.startTime).unix(),
      defaultSortOrder: 'descend',
    },
    {
      title: 'Duration',
      key: 'duration',
      width: 80,
      render: (_, record) => (
        <Text>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {calculateDuration(record.startTime, record.endTime)}
        </Text>
      ),
    },
    {
      title: 'Turns',
      dataIndex: 'turnCount',
      key: 'turnCount',
      width: 70,
      render: (count: number) => <Tag color="blue">{count || 0}</Tag>,
    },
    {
      title: 'End Reason',
      dataIndex: 'endReason',
      key: 'endReason',
      width: 120,
      render: (reason: string) => reason ? <Tag>{reason}</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: 'Labels',
      dataIndex: 'labels',
      key: 'labels',
      width: 200,
      render: (labels: CallLabels) => {
        if (!labels || Object.keys(labels).length === 0) {
          return <Text type="secondary">-</Text>;
        }
        const labelTags: any[] = [];
        Object.entries(labels).forEach(([labelId, value]) => {
          const config = labelConfigs.find(c => c.label_id === labelId);
          if (config) {
            if (Array.isArray(value)) {
              value.forEach(v => labelTags.push(<Tag key={`${labelId}-${v}`} color="purple">{v}</Tag>));
            } else {
              labelTags.push(<Tag key={labelId} color="blue">{value}</Tag>);
            }
          }
        });
        return <Space wrap>{labelTags.slice(0, 3)}{labelTags.length > 3 && <Text type="secondary">+{labelTags.length - 3}</Text>}</Space>;
      },
    },
    {
      title: 'Action',
      key: 'action',
      width: 250,
      render: (_, record) => (
        <Space wrap>
          <Button
            type="link"
            icon={<MessageOutlined />}
            onClick={() => handleViewTranscript(record)}
            disabled={!record.transcript || record.transcript.length === 0}
          >
            View
          </Button>
          <Button
            type="link"
            icon={<TagsOutlined />}
            onClick={() => handleOpenLabelModal(record)}
          >
            Label
          </Button>
          <Button
            type="link"
            icon={<ThunderboltOutlined />}
            onClick={() => handleAutoLabel(record.callSid)}
            loading={autoLabeling}
            disabled={!record.transcript || record.transcript.length === 0}
          >
            Auto
          </Button>
          <Button
            type="link"
            icon={<FileTextOutlined />}
            onClick={() => {
              setLogViewerCallSid(record.callSid);
              setLogViewerVisible(true);
            }}
          >
            Logs
          </Button>
          <Button
            type="link"
            icon={<DownloadOutlined />}
            onClick={() => handleDownloadRecording(record.callSid)}
            disabled={!record.recordingS3Key}
          >
            Audio
          </Button>
          <Popconfirm
            title="Delete call record"
            description="Are you sure you want to delete this call record?"
            onConfirm={() => handleDelete(record.callSid)}
            okText="Yes"
            cancelText="No"
          >
            <Button
              type="link"
              danger
              icon={<DeleteOutlined />}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const renderTranscript = (transcript: TranscriptEntry[]) => {
    if (!transcript || transcript.length === 0) {
      return <Empty description="No transcript available" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }

    return (
      <div style={{ maxHeight: 500, overflowY: 'auto', padding: 16, backgroundColor: '#f5f5f5', borderRadius: 6 }}>
        {transcript.map((entry, idx) => {
          const isUser = entry.role === 'user';
          return (
            <div
              key={idx}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: isUser ? 'flex-end' : 'flex-start',
                marginBottom: 16,
              }}
            >
              <Space size={4} style={{ marginBottom: 4 }}>
                {isUser ? <UserOutlined /> : <RobotOutlined />}
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {isUser ? 'Customer' : 'Assistant'}
                </Text>
                {entry.timestamp && (
                  <Text type="secondary" style={{ fontSize: 10 }}>
                    {dayjs(entry.timestamp).format('HH:mm:ss')}
                  </Text>
                )}
              </Space>
              <div
                style={{
                  maxWidth: '80%',
                  padding: '8px 12px',
                  borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                  backgroundColor: isUser ? '#1668dc' : '#e6f7ff',
                }}
              >
                <Text style={{ color: isUser ? '#fff' : 'rgba(0,0,0,0.85)' }}>{entry.text}</Text>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card className="glass-card fade-in" size="small">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={4} style={{ margin: 0 }}>Call History & Transcripts</Title>
            <Button onClick={fetchCallRecords} loading={loading}>
              Refresh
            </Button>
          </div>

          <Space wrap>
            <Search
              placeholder="Search by name, phone, or call SID"
              allowClear
              style={{ width: 300 }}
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
            <Select
              style={{ width: 150 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { label: 'All Status', value: 'all' },
                { label: 'Active', value: 'active' },
                { label: 'Completed', value: 'completed' },
              ]}
            />
            <Text type="secondary">
              Showing {filteredRecords.length} of {callRecords.length} records
            </Text>
          </Space>
        </Space>
      </Card>

      <Card className="glass-card fade-in" size="small">
        <Table
          columns={columns}
          dataSource={filteredRecords}
          rowKey="callSid"
          loading={loading}
          pagination={{
            defaultPageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            showTotal: (total) => `Total ${total} calls`,
          }}
          scroll={{ x: 1200 }}
        />
      </Card>

      <Modal
        title={
          <Space>
            <MessageOutlined />
            <span>Call Transcript</span>
          </Space>
        }
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        width={800}
        footer={[
          selectedCall?.recordingS3Key && (
            <Button
              key="download"
              icon={<DownloadOutlined />}
              onClick={() => handleDownloadRecording(selectedCall.callSid)}
            >
              Download Recording
            </Button>
          ),
          <Button key="close" onClick={() => setModalVisible(false)}>
            Close
          </Button>,
        ]}
      >
        {selectedCall ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="Call SID">
                <Text code>{selectedCall.callSid}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Status">
                <Tag color={selectedCall.status === 'completed' ? 'green' : 'blue'}>
                  {selectedCall.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Customer">
                {selectedCall.customerName || 'Unknown'}
              </Descriptions.Item>
              <Descriptions.Item label="Phone">
                {selectedCall.customerPhone || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Voice">
                <Tag>{selectedCall.voiceId || 'default'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Turns">
                <Tag color="blue">{selectedCall.turnCount || 0}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Start Time">
                {selectedCall.startTime ? dayjs(selectedCall.startTime).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="End Time">
                {selectedCall.endTime ? dayjs(selectedCall.endTime).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Duration" span={2}>
                {calculateDuration(selectedCall.startTime, selectedCall.endTime)}
              </Descriptions.Item>
              <Descriptions.Item label="End Reason" span={2}>
                {selectedCall.endReason || '-'}
              </Descriptions.Item>
            </Descriptions>

            <div>
              <Text strong style={{ fontSize: 14 }}>Transcript:</Text>
              <div style={{ marginTop: 8 }}>
                {renderTranscript(selectedCall.transcript || [])}
              </div>
            </div>
          </Space>
        ) : (
          <Spin />
        )}
      </Modal>

      {/* Label Editor Modal */}
      <Modal
        title={
          <Space>
            <TagsOutlined />
            <span>Edit Labels</span>
          </Space>
        }
        open={labelModalVisible}
        onCancel={() => setLabelModalVisible(false)}
        onOk={handleSaveLabels}
        width={600}
        okText="Save"
      >
        {labelingCall && (
          <Space direction="vertical" size={16} style={{ width: '100%', marginTop: 20 }}>
            <Descriptions size="small" bordered>
              <Descriptions.Item label="Call SID" span={3}>
                <Text code>{labelingCall.callSid}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Customer" span={3}>
                {labelingCall.customerName || 'Unknown'}
              </Descriptions.Item>
            </Descriptions>

            <Form form={labelForm} layout="vertical">
              {labelConfigs.map(config => (
                <Form.Item
                  key={config.label_id}
                  name={config.label_id}
                  label={
                    <Space>
                      <Text strong>{config.label_name}</Text>
                      {config.description && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          ({config.description})
                        </Text>
                      )}
                    </Space>
                  }
                >
                  {config.label_type === 'single' ? (
                    <Radio.Group>
                      <Space direction="vertical">
                        {config.options.map(option => (
                          <Radio key={option} value={option}>
                            {option}
                          </Radio>
                        ))}
                      </Space>
                    </Radio.Group>
                  ) : (
                    <Checkbox.Group>
                      <Space direction="vertical">
                        {config.options.map(option => (
                          <Checkbox key={option} value={option}>
                            {option}
                          </Checkbox>
                        ))}
                      </Space>
                    </Checkbox.Group>
                  )}
                </Form.Item>
              ))}
            </Form>

            {labelConfigs.length === 0 && (
              <Empty description="No label configurations found. Please create labels first." />
            )}
          </Space>
        )}
      </Modal>

      <LogViewer
        callSid={logViewerCallSid}
        visible={logViewerVisible}
        onClose={() => setLogViewerVisible(false)}
      />
    </div>
  );
}
