import { useState, useEffect } from 'react';
import { Card, Table, Button, Select, Space, Typography, Tag, message, Modal, Form, Input, Popconfirm } from 'antd';
import { ReloadOutlined, PhoneOutlined, UserOutlined, DeleteOutlined, EditOutlined, PlusOutlined, UploadOutlined, TagsOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listCustomers, deleteCustomer, makeCall, makeBatchCall, updateCustomer, importCustomers, listFlows, listPrompts, listLabels } from '../api';
import type { Customer, FlowConfig, PromptConfig, LabelConfig, CallLabels } from '../types';
import { useProject } from '../contexts/ProjectContext';

const { Title, Text } = Typography;
const { TextArea } = Input;

export function CustomerManagement() {
  const { currentProject } = useProject();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [callModalVisible, setCallModalVisible] = useState(false);
  const [batchCallModalVisible, setBatchCallModalVisible] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [callingCustomerId, setCallingCustomerId] = useState<string | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [csvContent, setCsvContent] = useState('');
  const [flows, setFlows] = useState<FlowConfig[]>([]);
  const [selectedFlowId, setSelectedFlowId] = useState<string>('');
  const [batchSelectedFlowId, setBatchSelectedFlowId] = useState<string>('');
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);
  const [labelConfigs, setLabelConfigs] = useState<LabelConfig[]>([]);

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      const data = await listCustomers(statusFilter, 100, currentProject?.project_id);
      setCustomers(data.customers);
    } catch (error) {
      console.error('Failed to fetch customers:', error);
      message.error('Failed to load customers');
    } finally {
      setLoading(false);
    }
  };

  const fetchFlows = async () => {
    try {
      const data = await listFlows(true, currentProject?.project_id);
      setFlows(data.flows);
    } catch (error) {
      console.error('Failed to fetch flows:', error);
    }
  };

  const fetchPrompts = async () => {
    try {
      // Load all prompts including system defaults (no project filter)
      const data = await listPrompts(true);
      setPrompts(data.prompts);
    } catch (error) {
      console.error('Failed to fetch prompts:', error);
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

  useEffect(() => {
    fetchCustomers();
    fetchFlows();
    fetchPrompts();
    fetchLabelConfigs();
  }, [statusFilter, currentProject]);

  const handleDelete = async (customerId: string) => {
    try {
      await deleteCustomer(customerId);
      message.success('Customer deleted');
      fetchCustomers();
    } catch (error) {
      message.error('Failed to delete customer');
    }
  };

  const handleCreate = () => {
    createForm.resetFields();
    setCreateModalVisible(true);
  };

  const handleCreateSubmit = async () => {
    try {
      const values = await createForm.validateFields();
      // Use import with single-row CSV, passing current project_id
      const csvData = `customer_name,phone_number,email,notes,voice_id,prompt_id\n${values.customer_name},${values.phone_number},${values.email || ''},${values.notes || ''},${values.voice_id || ''},${values.prompt_id || ''}`;
      await importCustomers(csvData, currentProject?.project_id);
      message.success('Customer created');
      setCreateModalVisible(false);
      fetchCustomers();
    } catch (error) {
      message.error('Failed to create customer');
    }
  };

  const handleEdit = (customer: Customer) => {
    setEditingCustomer(customer);
    editForm.setFieldsValue({
      customer_name: customer.customer_name,
      phone_number: customer.phone_number,
      email: customer.email,
      notes: customer.notes,
      voice_id: customer.voice_id,
      prompt_id: customer.prompt_id
    });
    setEditModalVisible(true);
  };

  const handleEditSubmit = async () => {
    if (!editingCustomer) return;

    try {
      const values = await editForm.validateFields();
      await updateCustomer(editingCustomer.customer_id, values);
      message.success('Customer updated');
      setEditModalVisible(false);
      fetchCustomers();
    } catch (error) {
      message.error('Failed to update customer');
    }
  };

  const handleCallClick = (customerId: string) => {
    if (flows.length === 0) {
      message.error('No active flows available. Please configure flows first.');
      return;
    }
    setCallingCustomerId(customerId);
    setSelectedFlowId('');
    setCallModalVisible(true);
  };

  const handleCall = async () => {
    if (!selectedFlowId) {
      message.error('Please select a flow');
      return;
    }

    if (!callingCustomerId) return;

    try {
      await makeCall(callingCustomerId, selectedFlowId);
      message.success('Call initiated');
      setCallModalVisible(false);
      fetchCustomers();
    } catch (error) {
      message.error('Failed to initiate call');
    }
  };

  const handleBatchCallClick = () => {
    if (selectedRowKeys.length === 0) {
      message.warning('Please select customers first');
      return;
    }

    if (flows.length === 0) {
      message.error('No active flows available. Please configure flows first.');
      return;
    }

    setBatchSelectedFlowId('');
    setBatchCallModalVisible(true);
  };

  const handleBatchCall = async () => {
    if (!batchSelectedFlowId) {
      message.error('Please select a flow');
      return;
    }

    try {
      const result = await makeBatchCall(selectedRowKeys, batchSelectedFlowId);
      message.success(`Calls initiated: ${result.success_count} success, ${result.failed_count} failed`);
      setBatchCallModalVisible(false);
      setSelectedRowKeys([]);
      fetchCustomers();
    } catch (error) {
      message.error('Failed to initiate batch calls');
    }
  };

  const handleImport = async () => {
    if (!csvContent.trim()) {
      message.error('Please paste CSV content');
      return;
    }

    try {
      const result = await importCustomers(csvContent, currentProject?.project_id);
      message.success(`Imported: ${result.imported}, Updated: ${result.updated}, Skipped: ${result.skipped}`);
      setImportModalVisible(false);
      setCsvContent('');
      fetchCustomers();
    } catch (error) {
      message.error('Failed to import customers');
    }
  };

  const getStatusTag = (status: string) => {
    const colorMap: Record<string, string> = {
      'pending': 'default',
      'calling': 'processing',
      'called': 'success',
      'completed': 'cyan',
      'failed': 'error'
    };
    return <Tag color={colorMap[status]}>{status.charAt(0).toUpperCase() + status.slice(1)}</Tag>;
  };

  const columns: ColumnsType<Customer> = [
    {
      title: 'Name',
      dataIndex: 'customer_name',
      key: 'customer_name',
      render: (name: string) => (
        <Space>
          <UserOutlined />
          <Text strong>{name || 'Unknown'}</Text>
        </Space>
      ),
    },
    {
      title: 'Phone',
      dataIndex: 'phone_number',
      key: 'phone_number',
      render: (phone: string) => <Text code>{phone}</Text>,
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
      render: (email: string) => <Text type="secondary">{email || '-'}</Text>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: getStatusTag,
      filters: [
        { text: 'Pending', value: 'pending' },
        { text: 'Calling', value: 'calling' },
        { text: 'Called', value: 'called' },
        { text: 'Completed', value: 'completed' },
        { text: 'Failed', value: 'failed' },
      ],
      onFilter: (value, record) => record.status === value,
    },
    {
      title: 'Calls',
      dataIndex: 'call_count',
      key: 'call_count',
      render: (count: number) => <Tag color="blue">{count || 0}</Tag>,
    },
    {
      title: 'Last Call',
      dataIndex: 'last_call_time',
      key: 'last_call_time',
      render: (time: string) => time ? dayjs(time).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: 'Labels',
      dataIndex: 'latest_call_labels',
      key: 'latest_call_labels',
      width: 250,
      render: (labels: CallLabels) => {
        if (!labels || Object.keys(labels).length === 0) {
          return <Text type="secondary">-</Text>;
        }
        const labelTags: any[] = [];
        Object.entries(labels).forEach(([labelId, value]) => {
          const config = labelConfigs.find(c => c.label_id === labelId);
          if (config) {
            if (Array.isArray(value)) {
              value.forEach(v => labelTags.push(
                <Tag key={`${labelId}-${v}`} color="purple" icon={<TagsOutlined />}>
                  {config.label_name}: {v}
                </Tag>
              ));
            } else {
              labelTags.push(
                <Tag key={labelId} color="blue" icon={<TagsOutlined />}>
                  {config.label_name}: {value}
                </Tag>
              );
            }
          }
        });
        return <Space wrap size="small">{labelTags}</Space>;
      },
    },
    {
      title: 'Notes',
      dataIndex: 'notes',
      key: 'notes',
      ellipsis: true,
      render: (notes: string) => <Text type="secondary">{notes || '-'}</Text>,
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<PhoneOutlined />}
            onClick={() => handleCallClick(record.customer_id)}
          >
            Call
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title="Delete customer?"
            onConfirm={() => handleDelete(record.customer_id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        className="glass-card"
        title={
          <Space>
            <UserOutlined />
            <Title level={4} style={{ margin: 0 }}>Customer Management</Title>
          </Space>
        }
        extra={
          <Space>
            <Select
              placeholder="Filter by status"
              allowClear
              style={{ width: 150 }}
              onChange={setStatusFilter}
              options={[
                { label: 'Pending', value: 'pending' },
                { label: 'Calling', value: 'calling' },
                { label: 'Called', value: 'called' },
                { label: 'Completed', value: 'completed' },
                { label: 'Failed', value: 'failed' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={fetchCustomers}>
              Refresh
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreate}
            >
              Add Customer
            </Button>
            <Button
              icon={<UploadOutlined />}
              onClick={() => setImportModalVisible(true)}
            >
              Import CSV
            </Button>
            {selectedRowKeys.length > 0 && (
              <Button
                type="primary"
                icon={<PhoneOutlined />}
                onClick={handleBatchCallClick}
              >
                Call Selected ({selectedRowKeys.length})
              </Button>
            )}
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={customers}
          rowKey="customer_id"
          loading={loading}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as string[]),
          }}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} customers`,
          }}
        />
      </Card>

      {/* Create Customer Modal */}
      <Modal
        title="Add New Customer"
        open={createModalVisible}
        onOk={handleCreateSubmit}
        onCancel={() => setCreateModalVisible(false)}
        width={600}
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 24 }}>
          <Form.Item
            name="customer_name"
            label="Customer Name"
            rules={[{ required: true, message: 'Please enter customer name' }]}
          >
            <Input placeholder="John Doe" />
          </Form.Item>

          <Form.Item
            name="phone_number"
            label="Phone Number"
            rules={[{ required: true, message: 'Please enter phone number' }]}
          >
            <Input placeholder="+1234567890" />
          </Form.Item>

          <Form.Item name="email" label="Email Address">
            <Input placeholder="john@example.com" type="email" />
          </Form.Item>

          <Form.Item name="notes" label="Notes">
            <TextArea
              rows={3}
              placeholder="Additional information about this customer"
            />
          </Form.Item>

          <Form.Item name="voice_id" label="Voice ID (Optional)">
            <Select
              placeholder="Select voice"
              allowClear
              showSearch
              options={[
                { label: 'Tiffany - English US (Female)', value: 'tiffany' },
                { label: 'Matthew - English US (Male)', value: 'matthew' },
                { label: 'Amy - English UK (Female)', value: 'amy' },
                { label: 'Olivia - English AU (Female)', value: 'olivia' },
                { label: 'Kiara - English IN (Female)', value: 'kiara' },
                { label: 'Arjun - English IN (Male)', value: 'arjun' },
                { label: 'Ambre - French (Female)', value: 'ambre' },
                { label: 'Florian - French (Male)', value: 'florian' },
                { label: 'Beatrice - Italian (Female)', value: 'beatrice' },
                { label: 'Lorenzo - Italian (Male)', value: 'lorenzo' },
                { label: 'Tina - German (Female)', value: 'tina' },
                { label: 'Lennart - German (Male)', value: 'lennart' },
                { label: 'Lupe - Spanish US (Female)', value: 'lupe' },
                { label: 'Carlos - Spanish US (Male)', value: 'carlos' },
                { label: 'Carolina - Portuguese BR (Female)', value: 'carolina' },
                { label: 'Leo - Portuguese BR (Male)', value: 'leo' },
              ]}
            />
          </Form.Item>

          <Form.Item name="prompt_id" label="Prompt Template (Optional)">
            <Select
              placeholder="Select prompt"
              allowClear
              options={prompts.map(p => ({
                label: p.prompt_name,
                value: p.prompt_id
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Customer Modal */}
      <Modal
        title="Edit Customer"
        open={editModalVisible}
        onOk={handleEditSubmit}
        onCancel={() => setEditModalVisible(false)}
        width={600}
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 24 }}>
          <Form.Item
            name="customer_name"
            label="Customer Name"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="phone_number"
            label="Phone Number"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>

          <Form.Item name="email" label="Email Address">
            <Input type="email" />
          </Form.Item>

          <Form.Item name="notes" label="Notes">
            <TextArea rows={3} />
          </Form.Item>

          <Form.Item name="voice_id" label="Voice ID">
            <Select
              allowClear
              showSearch
              options={[
                { label: 'Tiffany - English US (Female)', value: 'tiffany' },
                { label: 'Matthew - English US (Male)', value: 'matthew' },
                { label: 'Amy - English UK (Female)', value: 'amy' },
                { label: 'Olivia - English AU (Female)', value: 'olivia' },
                { label: 'Kiara - English IN (Female)', value: 'kiara' },
                { label: 'Arjun - English IN (Male)', value: 'arjun' },
                { label: 'Ambre - French (Female)', value: 'ambre' },
                { label: 'Florian - French (Male)', value: 'florian' },
                { label: 'Beatrice - Italian (Female)', value: 'beatrice' },
                { label: 'Lorenzo - Italian (Male)', value: 'lorenzo' },
                { label: 'Tina - German (Female)', value: 'tina' },
                { label: 'Lennart - German (Male)', value: 'lennart' },
                { label: 'Lupe - Spanish US (Female)', value: 'lupe' },
                { label: 'Carlos - Spanish US (Male)', value: 'carlos' },
                { label: 'Carolina - Portuguese BR (Female)', value: 'carolina' },
                { label: 'Leo - Portuguese BR (Male)', value: 'leo' },
              ]}
            />
          </Form.Item>

          <Form.Item name="prompt_id" label="Prompt Template">
            <Select
              allowClear
              options={prompts.map(p => ({
                label: p.prompt_name,
                value: p.prompt_id
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Import CSV Modal */}
      <Modal
        title="Import Customers from CSV"
        open={importModalVisible}
        onOk={handleImport}
        onCancel={() => setImportModalVisible(false)}
        width={700}
      >
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div>
            <Title level={5}>CSV Format</Title>
            <Text type="secondary">
              Paste your CSV content below. Required columns:
            </Text>
            <pre style={{
              background: '#f5f5f5',
              padding: 12,
              borderRadius: 4,
              marginTop: 8,
              fontSize: 12
            }}>
customer_name,phone_number,email,notes,voice_id,prompt_id
John Doe,+1234567890,john@example.com,VIP customer,tiffany,prompt-id-123
Jane Smith,+0987654321,jane@example.com,Follow up next week,matthew,
            </pre>
          </div>

          <Form.Item label="CSV Content">
            <TextArea
              rows={10}
              placeholder="Paste CSV content here..."
              value={csvContent}
              onChange={(e) => setCsvContent(e.target.value)}
            />
          </Form.Item>
        </Space>
      </Modal>

      {/* Single Call Modal */}
      <Modal
        title="Initiate Call"
        open={callModalVisible}
        onOk={handleCall}
        onCancel={() => setCallModalVisible(false)}
      >
        <Form layout="vertical">
          <Form.Item label="Select Flow">
            <Select
              placeholder="Choose a call flow"
              value={selectedFlowId}
              onChange={setSelectedFlowId}
              options={flows.map(f => ({
                label: f.flow_name,
                value: f.flow_id
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Batch Call Modal */}
      <Modal
        title={`Batch Call (${selectedRowKeys.length} customers)`}
        open={batchCallModalVisible}
        onOk={handleBatchCall}
        onCancel={() => setBatchCallModalVisible(false)}
      >
        <Form layout="vertical">
          <Form.Item label="Select Flow">
            <Select
              placeholder="Choose a call flow"
              value={batchSelectedFlowId}
              onChange={setBatchSelectedFlowId}
              options={flows.map(f => ({
                label: f.flow_name,
                value: f.flow_id
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
