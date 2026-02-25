import { useState, useEffect } from 'react';
import { Card, Table, Button, Select, Space, Typography, Tag, message, Modal, Form, Input, InputNumber, Popconfirm, Alert } from 'antd';
import { ReloadOutlined, PhoneOutlined, UserOutlined, DeleteOutlined, EditOutlined, UploadOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listCustomers, deleteCustomer, makeCall, makeBatchCall, updateCustomer, importCustomers, listFlows, listPrompts } from '../api';
import type { Customer, FlowConfig, PromptConfig } from '../types';

const { Title, Text } = Typography;
const { TextArea } = Input;

export function CustomerManagement() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [callModalVisible, setCallModalVisible] = useState(false);
  const [batchCallModalVisible, setBatchCallModalVisible] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [callingCustomerId, setCallingCustomerId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [csvContent, setCsvContent] = useState('');
  const [flows, setFlows] = useState<FlowConfig[]>([]);
  const [selectedFlowId, setSelectedFlowId] = useState<string>('');
  const [batchSelectedFlowId, setBatchSelectedFlowId] = useState<string>('');
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      const data = await listCustomers(statusFilter);
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
      const data = await listFlows(true);
      setFlows(data.flows);
    } catch (error) {
      console.error('Failed to fetch flows:', error);
    }
  };

  const fetchPrompts = async () => {
    try {
      const data = await listPrompts(true);
      setPrompts(data.prompts);
    } catch (error) {
      console.error('Failed to fetch prompts:', error);
    }
  };

  useEffect(() => {
    fetchCustomers();
    fetchFlows();
    fetchPrompts();
  }, [statusFilter]);

  const handleDelete = async (customerId: string) => {
    try {
      await deleteCustomer(customerId);
      message.success('Customer deleted');
      fetchCustomers();
    } catch (error) {
      message.error('Failed to delete customer');
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

  const handleEdit = (customer: Customer) => {
    setEditingCustomer(customer);
    form.setFieldsValue({
      customer_name: customer.customer_name,
      phone_number: customer.phone_number,
      debt_amount: customer.debt_amount,
      notes: customer.notes,
      voice_id: customer.voice_id,
      prompt_id: customer.prompt_id
    });
    setEditModalVisible(true);
  };

  const handleEditSubmit = async () => {
    if (!editingCustomer) return;

    try {
      const values = await form.validateFields();
      await updateCustomer(editingCustomer.customer_id, values);
      message.success('Customer updated');
      setEditModalVisible(false);
      fetchCustomers();
    } catch (error) {
      message.error('Failed to update customer');
    }
  };

  const handleImport = async () => {
    if (!csvContent.trim()) {
      message.error('Please paste CSV content');
      return;
    }

    try {
      const result = await importCustomers(csvContent);
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
      'failed': 'error'
    };
    const labelMap: Record<string, string> = {
      'pending': 'Pending',
      'calling': 'Calling',
      'called': 'Called',
      'failed': 'Failed'
    };
    return <Tag color={colorMap[status]}>{labelMap[status] || status}</Tag>;
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
      render: (phone: string) => (
        <Text code>{phone}</Text>
      ),
    },
    {
      title: 'Debt',
      dataIndex: 'debt_amount',
      key: 'debt_amount',
      render: (amount: number) => (
        <Tag color="red">${amount}</Tag>
      ),
      sorter: (a, b) => a.debt_amount - b.debt_amount,
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
        { text: 'Failed', value: 'failed' },
      ],
      onFilter: (value, record) => record.status === value,
    },
    {
      title: 'Calls',
      dataIndex: 'call_count',
      key: 'call_count',
      render: (count: number) => <Tag>{count}</Tag>,
    },
    {
      title: 'Last Call',
      dataIndex: 'last_call_time',
      key: 'last_call_time',
      render: (time: string) => (
        time ? dayjs(time).format('MM-DD HH:mm') : <Text type="secondary">Never</Text>
      ),
    },
    {
      title: 'Voice ID',
      dataIndex: 'voice_id',
      key: 'voice_id',
      render: (voiceId: string) => (
        voiceId ? <Text type="secondary" style={{ fontSize: '12px' }}>{voiceId}</Text> : <Text type="secondary">-</Text>
      ),
    },
    {
      title: 'System Prompt',
      dataIndex: 'prompt_id',
      key: 'prompt_id',
      render: (promptId: string) => {
        if (!promptId) return <Text type="secondary">-</Text>;
        const prompt = prompts.find(p => p.prompt_id === promptId);
        return prompt ? <Text style={{ fontSize: '12px' }}>{prompt.prompt_name}</Text> : <Text type="secondary">Unknown</Text>;
      },
    },
    {
      title: 'Notes',
      dataIndex: 'notes',
      key: 'notes',
      render: (notes: string) => (
        notes ? (
          <Text ellipsis style={{ maxWidth: 200 }} title={notes}>
            {notes}
          </Text>
        ) : <Text type="secondary">-</Text>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<PhoneOutlined />}
            onClick={() => handleCallClick(record.customer_id)}
            disabled={record.status === 'calling'}
          >
            Call
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete this customer?"
            onConfirm={() => handleDelete(record.customer_id)}
            okText="Yes"
            cancelText="No"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys as string[]);
    },
  };

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            <UserOutlined style={{ marginRight: 8 }} />
            Customer Management
          </Title>
          <Space>
            <Select
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: 150 }}
              allowClear
              placeholder="Filter by status"
              options={[
                { value: 'pending', label: 'Pending' },
                { value: 'calling', label: 'Calling' },
                { value: 'called', label: 'Called' },
                { value: 'failed', label: 'Failed' },
              ]}
            />
            <Button
              icon={<UploadOutlined />}
              onClick={() => setImportModalVisible(true)}
            >
              Import CSV
            </Button>
            <Button
              type="primary"
              icon={<PhoneOutlined />}
              onClick={handleBatchCallClick}
              disabled={selectedRowKeys.length === 0}
            >
              Batch Call ({selectedRowKeys.length})
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchCustomers}
              loading={loading}
            >
              Refresh
            </Button>
          </Space>
        </div>

        <Table
          columns={columns}
          dataSource={customers}
          rowKey="customer_id"
          loading={loading}
          rowSelection={rowSelection}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} customers`,
          }}
          size="small"
        />
      </Space>

      {/* Edit Modal */}
      <Modal
        title="Edit Customer"
        open={editModalVisible}
        onOk={handleEditSubmit}
        onCancel={() => setEditModalVisible(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="customer_name"
            label="Customer Name"
            rules={[{ required: true, message: 'Please enter customer name' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="phone_number"
            label="Phone Number"
            rules={[{ required: true, message: 'Please enter phone number' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="debt_amount"
            label="Debt Amount"
            rules={[{ required: true, message: 'Please enter debt amount' }]}
          >
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="voice_id" label="Voice ID">
            <Select placeholder="Select voice" allowClear>
              <Select.Option value="tiffany">Tiffany (en-US, Female)</Select.Option>
              <Select.Option value="matthew">Matthew (en-US, Male)</Select.Option>
              <Select.Option value="amy">Amy (en-GB, Female)</Select.Option>
              <Select.Option value="olivia">Olivia (en-AU, Female)</Select.Option>
              <Select.Option value="kiara">Kiara (en-IN/hi-IN, Female)</Select.Option>
              <Select.Option value="arjun">Arjun (en-IN/hi-IN, Male)</Select.Option>
              <Select.Option value="ambre">Ambre (fr-FR, Female)</Select.Option>
              <Select.Option value="florian">Florian (fr-FR, Male)</Select.Option>
              <Select.Option value="beatrice">Beatrice (it-IT, Female)</Select.Option>
              <Select.Option value="lorenzo">Lorenzo (it-IT, Male)</Select.Option>
              <Select.Option value="tina">Tina (de-DE, Female)</Select.Option>
              <Select.Option value="lennart">Lennart (de-DE, Male)</Select.Option>
              <Select.Option value="lupe">Lupe (es-US, Female)</Select.Option>
              <Select.Option value="carlos">Carlos (es-US, Male)</Select.Option>
              <Select.Option value="carolina">Carolina (pt-BR, Female)</Select.Option>
              <Select.Option value="leo">Leo (pt-BR, Male)</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="prompt_id" label="System Prompt">
            <Select placeholder="Select prompt template" allowClear>
              {prompts.map(prompt => (
                <Select.Option key={prompt.prompt_id} value={prompt.prompt_id}>
                  {prompt.prompt_name}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* Import Modal */}
      <Modal
        title="Import Customers from CSV"
        open={importModalVisible}
        onOk={handleImport}
        onCancel={() => setImportModalVisible(false)}
        width={600}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>Paste your CSV content below:</Text>
          <Text type="secondary" code>
            customer_name,phone_number,debt_amount
          </Text>
          <TextArea
            rows={10}
            value={csvContent}
            onChange={(e) => setCsvContent(e.target.value)}
            placeholder="customer_name,phone_number,debt_amount&#10;John Doe,+1234567890,1000&#10;Jane Smith,+9876543210,500"
          />
          <Text type="secondary">
            <CheckCircleOutlined style={{ color: 'green', marginRight: 4 }} />
            Duplicate phone numbers will be updated automatically
          </Text>
        </Space>
      </Modal>

      {/* Single Call Flow Selection Modal */}
      <Modal
        title="Select Flow for Call"
        open={callModalVisible}
        onOk={handleCall}
        onCancel={() => setCallModalVisible(false)}
        okText="Make Call"
        okButtonProps={{ disabled: !selectedFlowId }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            message="Flow Selection Required"
            description="You must select a contact flow before making the call."
            type="info"
            showIcon
          />
          <Text strong>Select Contact Flow:</Text>
          <Select
            style={{ width: '100%' }}
            placeholder="Choose a flow"
            value={selectedFlowId}
            onChange={setSelectedFlowId}
            options={flows.map(flow => ({
              value: flow.flow_id,
              label: flow.flow_name,
              description: flow.description
            }))}
            optionRender={(option) => (
              <Space direction="vertical" size={0}>
                <Text strong>{option.data.label}</Text>
                {option.data.description && (
                  <Text type="secondary" style={{ fontSize: '12px' }}>
                    {option.data.description}
                  </Text>
                )}
              </Space>
            )}
          />
        </Space>
      </Modal>

      {/* Batch Call Flow Selection Modal */}
      <Modal
        title={`Batch Call - ${selectedRowKeys.length} Customers`}
        open={batchCallModalVisible}
        onOk={handleBatchCall}
        onCancel={() => setBatchCallModalVisible(false)}
        okText="Start Batch Calls"
        okButtonProps={{ disabled: !batchSelectedFlowId }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            message="Batch Call Confirmation"
            description={`You are about to call ${selectedRowKeys.length} customers. All calls will use the same contact flow.`}
            type="warning"
            showIcon
          />
          <Text strong>Select Contact Flow:</Text>
          <Select
            style={{ width: '100%' }}
            placeholder="Choose a flow"
            value={batchSelectedFlowId}
            onChange={setBatchSelectedFlowId}
            options={flows.map(flow => ({
              value: flow.flow_id,
              label: flow.flow_name,
              description: flow.description
            }))}
            optionRender={(option) => (
              <Space direction="vertical" size={0}>
                <Text strong>{option.data.label}</Text>
                {option.data.description && (
                  <Text type="secondary" style={{ fontSize: '12px' }}>
                    {option.data.description}
                  </Text>
                )}
              </Space>
            )}
          />
        </Space>
      </Modal>
    </Card>
  );
}
